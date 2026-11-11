import { useCallback, useEffect, useRef } from "react";
import { stopRecording, uploadRecordingChunk } from "../api/roomLiveApi";

const LARGEUR = 1280;
const HAUTEUR = 720;
const FPS = 15;
const TRANCHE_MS = 5000;
const ESSAIS_ENVOI = 4;

function choisirFormat() {
  const candidats = ["video/webm;codecs=vp9,opus", "video/webm;codecs=vp8,opus", "video/webm"];
  return candidats.find((f) => window.MediaRecorder?.isTypeSupported?.(f)) || "";
}

const attendre = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/**
 * Enregistrement côté navigateur de l'hôte / du co-hôte : mosaïque vidéo (canvas) + mélange audio
 * (Web Audio), encodés par MediaRecorder et envoyés au serveur par fragments ordonnés.
 *
 * Consentement : un flux n'est mixé (image ET son) que si `getConsents()` renvoie "accepte" pour
 * ce participant ; les autres apparaissent comme « Non enregistré » et restent muets.
 *
 * `getSources()` renvoie [{ id, label, stream (image), audioStream (son, facultatif), local }] ; `getConsents()` renvoie { [id]: decision }.
 * Les deux sont lus à chaque image / seconde, donc toujours à jour sans relancer l'enregistrement.
 */
export default function useRoomRecorder({ getSources, getConsents, onError }) {
  const etat = useRef(null);

  const nettoyer = useCallback(() => {
    const e = etat.current;
    if (!e) return;
    clearInterval(e.minuteurDessin);
    clearInterval(e.minuteurAudio);
    try { e.recorder.state !== "inactive" && e.recorder.stop(); } catch {}
    e.audioSources.forEach((src) => { try { src.disconnect(); } catch {} });
    try { e.audioCtx.close(); } catch {}
    e.videos.forEach((v) => { v.srcObject = null; });
    etat.current = null;
  }, []);

  const start = useCallback(async (recId) => {
    if (etat.current) return;
    if (!window.MediaRecorder) throw new Error("Ce navigateur ne prend pas en charge l'enregistrement.");
    const canvas = document.createElement("canvas");
    canvas.width = LARGEUR; canvas.height = HAUTEUR;
    const ctx = canvas.getContext("2d");
    const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    await audioCtx.resume().catch(() => {});
    const destination = audioCtx.createMediaStreamDestination();
    const videos = new Map();       // id -> <video>
    const audioSources = new Map(); // id -> MediaStreamAudioSourceNode

    const synchroniserAudio = () => {
      const consents = getConsents();
      const sources = getSources();
      const voulus = new Set(sources.filter((s) => s.local || consents[s.id] === "accepte").map((s) => s.id));
      audioSources.forEach((src, id) => {
        if (!voulus.has(id)) { try { src.disconnect(); } catch {} audioSources.delete(id); }
      });
      sources.forEach((s) => {
        if (!voulus.has(s.id) || audioSources.has(s.id)) return;
        // Le son vient de `audioStream` (le micro reste capté pendant un partage d'écran) ; le mélange
        // n'est jamais relié aux haut-parleurs, donc aucun écho.
        const audio = s.audioStream || s.stream;
        if (!audio || audio.getAudioTracks().length === 0) return;
        const src = audioCtx.createMediaStreamSource(new MediaStream(audio.getAudioTracks()));
        src.connect(destination);
        audioSources.set(s.id, src);
      });
    };

    const dessiner = () => {
      const consents = getConsents();
      const sources = getSources();
      ctx.fillStyle = "#0f172a";
      ctx.fillRect(0, 0, LARGEUR, HAUTEUR);
      const n = Math.max(sources.length, 1);
      const colonnes = Math.ceil(Math.sqrt(n));
      const lignes = Math.ceil(n / colonnes);
      const w = LARGEUR / colonnes;
      const h = HAUTEUR / lignes;
      sources.forEach((s, i) => {
        const x = (i % colonnes) * w;
        const y = Math.floor(i / colonnes) * h;
        const autorise = s.local || consents[s.id] === "accepte";
        if (autorise && s.stream) {
          let video = videos.get(s.id);
          if (!video) {
            video = document.createElement("video");
            video.muted = true; video.playsInline = true;
            video.srcObject = s.stream;
            video.play().catch(() => {});
            videos.set(s.id, video);
          } else if (video.srcObject !== s.stream) {
            video.srcObject = s.stream;
          }
          if (video.videoWidth) {
            const ratio = Math.min((w - 8) / video.videoWidth, (h - 8) / video.videoHeight);
            const dw = video.videoWidth * ratio; const dh = video.videoHeight * ratio;
            ctx.drawImage(video, x + (w - dw) / 2, y + (h - dh) / 2, dw, dh);
          }
        } else {
          ctx.fillStyle = "#1e293b";
          ctx.fillRect(x + 4, y + 4, w - 8, h - 8);
          ctx.fillStyle = "#94a3b8";
          ctx.font = "22px sans-serif"; ctx.textAlign = "center";
          ctx.fillText("Non enregistré", x + w / 2, y + h / 2);
        }
        ctx.fillStyle = "#ffffffcc"; ctx.font = "16px sans-serif"; ctx.textAlign = "left";
        ctx.fillText(s.label || "", x + 14, y + h - 14);
      });
    };

    synchroniserAudio();
    const minuteurDessin = setInterval(dessiner, 1000 / FPS);
    const minuteurAudio = setInterval(synchroniserAudio, 1000);

    const flux = new MediaStream([
      ...canvas.captureStream(FPS).getVideoTracks(),
      ...destination.stream.getAudioTracks(),
    ]);
    const format = choisirFormat();
    const recorder = new MediaRecorder(flux, format ? { mimeType: format, videoBitsPerSecond: 1_500_000 } : undefined);

    const e = { recId, recorder, audioCtx, audioSources, videos, minuteurDessin, minuteurAudio,
      seq: 0, file: Promise.resolve(), arrete: false, echec: false };
    etat.current = e;

    const envoyer = async (blob, seq) => {
      for (let essai = 1; essai <= ESSAIS_ENVOI; essai += 1) {
        try { await uploadRecordingChunk(recId, seq, blob); return; }
        catch (err) {
          const definitif = /hors séquence|clos|terminé|trop volumineux|Taille maximale|Stockage/i.test(err.message);
          if (definitif || essai === ESSAIS_ENVOI) throw err;
          await attendre(800 * essai);
        }
      }
    };

    recorder.ondataavailable = (event) => {
      if (!event.data || event.data.size === 0 || e.echec) return;
      const seq = e.seq; e.seq += 1;
      // File d'attente : les fragments partent un par un, dans l'ordre, sans jamais se doubler.
      e.file = e.file.then(() => (e.echec ? null : envoyer(event.data, seq))).catch((err) => {
        if (!e.echec) { e.echec = true; onError?.(`Enregistrement interrompu : ${err.message}`); nettoyer(); }
      });
    };
    recorder.start(TRANCHE_MS);
  }, [getConsents, getSources, nettoyer, onError]);

  /** Arrête, envoie le dernier fragment, puis clôt l'enregistrement côté serveur. */
  const stop = useCallback(async () => {
    const e = etat.current;
    if (!e) return;
    const { recorder, recId } = e;
    await new Promise((resolve) => {
      recorder.addEventListener("stop", resolve, { once: true });
      try { recorder.state !== "inactive" ? recorder.stop() : resolve(); } catch { resolve(); }
    });
    await e.file;
    const echec = e.echec;
    nettoyer();
    if (!echec) await stopRecording(recId);
  }, [nettoyer]);

  /** Abandon local (sortie de salle, fermeture) : le serveur clôt de son côté. */
  const cancel = useCallback(() => nettoyer(), [nettoyer]);

  useEffect(() => nettoyer, [nettoyer]);

  // Fonctions stables (useCallback) : elles figurent dans les dépendances de connectRoom / exitRoom
  // et ne doivent pas les recréer à chaque rendu (sinon l'auto-connexion par lien se relancerait).
  const isActive = useCallback(() => Boolean(etat.current), []);
  return { start, stop, cancel, isActive };
}
