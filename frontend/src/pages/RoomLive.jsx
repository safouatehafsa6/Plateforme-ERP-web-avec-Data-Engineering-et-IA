import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Video, VideoOff, Mic, MicOff, MonitorUp, MonitorOff, PhoneOff,
  Plus, Users, MessageCircle, Paperclip, Lock, Globe, Send, UserPlus,
  Ban, X, Copy, Download, RefreshCw,
} from "lucide-react";
import {
  listRooms, createRoom, joinRoom, inviteRoom, removeParticipant,
  leaveRoom, shareFile, roomWebSocketUrl, downloadSharedFile,
} from "../api/roomLiveApi";
import "./room-live.css";

const rtcConfig = { iceServers: [{ urls: "stun:stun.l.google.com:19302" }] };

export default function RoomLive() {
  const { t } = useTranslation();
  const [rooms, setRooms] = useState([]);
  const [room, setRoom] = useState(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [isPrivate, setIsPrivate] = useState(true);
  const [chat, setChat] = useState([]);
  const [draft, setDraft] = useState("");
  const [participants, setParticipants] = useState([]);
  const [files, setFiles] = useState([]);
  const [inviteEmail, setInviteEmail] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [audioOn, setAudioOn] = useState(true);
  const [videoOn, setVideoOn] = useState(true);
  const [sharing, setSharing] = useState(false);
  const [remoteStreams, setRemoteStreams] = useState({});
  const [activeTab, setActiveTab] = useState("chat");
  const localVideo = useRef(null);
  const localStream = useRef(null);
  const screenStream = useRef(null);
  const ws = useRef(null);
  const peers = useRef({});
  const pendingCandidates = useRef({});
  const remoteVideoRefs = useRef({});
  const currentRoom = useRef(null);
  const userId = useRef("");

  const refreshRooms = useCallback(async () => {
    try { const data = await listRooms(); setRooms(data.rooms || []); }
    catch (e) { setError(e.message); }
  }, []);

  useEffect(() => { refreshRooms(); }, [refreshRooms]);


  const sendSignal = useCallback((payload) => {
    if (ws.current?.readyState === WebSocket.OPEN) ws.current.send(JSON.stringify(payload));
  }, []);

  const closePeers = useCallback(() => {
    Object.values(peers.current).forEach((pc) => pc.close());
    peers.current = {};
    pendingCandidates.current = {};
    setRemoteStreams({});
  }, []);

  const makePeer = useCallback((peerId) => {
    if (peers.current[peerId]) return peers.current[peerId];
    const pc = new RTCPeerConnection(rtcConfig);
    const stream = localStream.current;
    stream?.getTracks().forEach((track) => pc.addTrack(track, stream));
    pc.onicecandidate = (event) => {
      if (event.candidate) sendSignal({ type: "ice-candidate", target_user_id: peerId, payload: event.candidate });
    };
    pc.ontrack = (event) => {
      const incoming = event.streams[0];
      setRemoteStreams((old) => ({ ...old, [peerId]: incoming }));
    };
    pc.onconnectionstatechange = () => {
      if (["failed", "closed", "disconnected"].includes(pc.connectionState)) {
        setRemoteStreams((old) => { const next = { ...old }; delete next[peerId]; return next; });
      }
    };
    peers.current[peerId] = pc;
    return pc;
  }, [sendSignal]);

  const startMedia = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: true });
      localStream.current = stream;
      if (localVideo.current) localVideo.current.srcObject = stream;
      return stream;
    } catch (e) {
      setError("Accès caméra/micro refusé ou matériel indisponible : " + e.message);
      return null;
    }
  }, []);

  const connectRoom = useCallback(async (selectedRoom) => {
    setError("");
    setBusy(true);
    try {
      const joined = await joinRoom(selectedRoom.id);
      setRoom(joined.room);
      const currentUrl = new URL(window.location.href);
      if (currentUrl.searchParams.has("room")) {
        currentUrl.searchParams.delete("room");
        window.history.replaceState({}, "", currentUrl);
      }
      currentRoom.current = joined.room;
      setParticipants(joined.room.participants || []);
      setChat([]);
      await startMedia();
      const socket = new WebSocket(roomWebSocketUrl(selectedRoom.id));
      ws.current = socket;
      socket.onmessage = async (event) => {
        const data = JSON.parse(event.data);
        if (data.type === "history") setChat(data.messages || []);
        if (data.type === "participants" && data.room?.participants) {
          setParticipants(data.room.participants);
        }
        if (data.type === "chat") setChat((old) => [...old, data.message]);
        if (data.type === "file_shared") setFiles((old) => [...old, data.file]);
        if (data.type === "participant_removed" || data.type === "participant_blocked") {
          if (String(data.user_id) === String(userId.current)) {
            setError("Votre accès à cette salle a été retiré.");
            socket.close();
            setRoom(null);
            closePeers();
          }
        }
        if (data.type === "presence" && data.status === "joined" && String(data.user_id) !== String(userId.current)) {
          const pc = makePeer(String(data.user_id));
          try {
            const offer = await pc.createOffer();
            await pc.setLocalDescription(offer);
            sendSignal({ type: "offer", target_user_id: String(data.user_id), payload: pc.localDescription });
          } catch (e) { setError("Signalisation WebRTC : " + e.message); }
        }
        if (data.type === "offer") {
          const pc = makePeer(String(data.from_user_id));
          try {
            await pc.setRemoteDescription(new RTCSessionDescription(data.payload));
            for (const candidate of pendingCandidates.current[String(data.from_user_id)] || []) {
              try { await pc.addIceCandidate(new RTCIceCandidate(candidate)); } catch {}
            }
            delete pendingCandidates.current[String(data.from_user_id)];
            const answer = await pc.createAnswer();
            await pc.setLocalDescription(answer);
            sendSignal({ type: "answer", target_user_id: String(data.from_user_id), payload: pc.localDescription });
          } catch (e) { setError("Connexion vidéo : " + e.message); }
        }
        if (data.type === "answer") {
          const pc = peers.current[String(data.from_user_id)];
          if (pc) {
            await pc.setRemoteDescription(new RTCSessionDescription(data.payload));
            for (const candidate of pendingCandidates.current[String(data.from_user_id)] || []) {
              try { await pc.addIceCandidate(new RTCIceCandidate(candidate)); } catch {}
            }
            delete pendingCandidates.current[String(data.from_user_id)];
          }
        }
        if (data.type === "ice-candidate" && data.payload) {
          const peerId = String(data.from_user_id);
          const pc = peers.current[peerId];
          if (pc?.remoteDescription) {
            try { await pc.addIceCandidate(new RTCIceCandidate(data.payload)); } catch {}
          } else {
            pendingCandidates.current[peerId] = [...(pendingCandidates.current[peerId] || []), data.payload];
          }
        }
      };
      socket.onerror = () => setError("Connexion temps réel impossible. Vérifiez le serveur et le jeton de session.");
    } catch (e) { setError(e.message); setRoom(null); }
    finally { setBusy(false); }
  }, [closePeers, makePeer, sendSignal, startMedia]);

  useEffect(() => {
    const requestedRoom = new URLSearchParams(window.location.search).get("room");
    if (!room && requestedRoom && rooms.length) {
      const match = rooms.find((item) => item.id === requestedRoom);
      if (match) connectRoom(match);
    }
  }, [rooms, room, connectRoom]);

  useEffect(() => {
    const token = localStorage.getItem("token");
    try {
      const payload = JSON.parse(atob(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")));
      userId.current = String(payload.id || payload.sub || payload.email || "");
    } catch { userId.current = ""; }
  }, []);

  useEffect(() => {
    if (room && localVideo.current && localStream.current && localVideo.current.srcObject !== localStream.current) {
      localVideo.current.srcObject = localStream.current;
    }
  }, [room]);

  useEffect(() => {
    Object.entries(remoteStreams).forEach(([id, stream]) => {
      const element = remoteVideoRefs.current[id];
      if (element && element.srcObject !== stream) element.srcObject = stream;
    });
  }, [remoteStreams]);

  const exitRoom = useCallback(async () => {
    const id = currentRoom.current?.id;
    ws.current?.close();
    ws.current = null;
    closePeers();
    localStream.current?.getTracks().forEach((track) => track.stop());
    screenStream.current?.getTracks().forEach((track) => track.stop());
    localStream.current = null;
    screenStream.current = null;
    if (id) { try { await leaveRoom(id); } catch {} }
    setRoom(null);
    currentRoom.current = null;
    setSharing(false);
    refreshRooms();
  }, [closePeers, refreshRooms]);

  useEffect(() => () => {
    ws.current?.close();
    Object.values(peers.current).forEach((pc) => pc.close());
    localStream.current?.getTracks().forEach((track) => track.stop());
    screenStream.current?.getTracks().forEach((track) => track.stop());
  }, []);

  async function handleCreate(e) {
    e.preventDefault();
    setError("");
    try {
      const data = await createRoom({ name, description, is_private: isPrivate });
      setName(""); setDescription("");
      await refreshRooms();
      await connectRoom(data.room);
    } catch (e) { setError(e.message); }
  }

  function sendChat(e) {
    e.preventDefault();
    const content = draft.trim();
    if (!content) return;
    sendSignal({ type: "chat", content });
    setDraft("");
  }

  function toggleAudio() {
    const next = !audioOn;
    localStream.current?.getAudioTracks().forEach((track) => { track.enabled = next; });
    setAudioOn(next);
    sendSignal({ type: "media_state", audio: next, video: videoOn });
  }

  function toggleVideo() {
    const next = !videoOn;
    localStream.current?.getVideoTracks().forEach((track) => { track.enabled = next; });
    setVideoOn(next);
    sendSignal({ type: "media_state", audio: audioOn, video: next });
  }

  async function toggleScreen() {
    if (sharing) {
      const cameraTrack = localStream.current?.getVideoTracks()[0];
      Object.values(peers.current).forEach((pc) => {
        const sender = pc.getSenders().find((s) => s.track?.kind === "video");
        if (sender && cameraTrack) sender.replaceTrack(cameraTrack);
      });
      screenStream.current?.getTracks().forEach((track) => track.stop());
      screenStream.current = null;
      if (localVideo.current) localVideo.current.srcObject = localStream.current;
      setSharing(false);
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getDisplayMedia({ video: true });
      screenStream.current = stream;
      const track = stream.getVideoTracks()[0];
      Object.values(peers.current).forEach((pc) => {
        const sender = pc.getSenders().find((s) => s.track?.kind === "video");
        if (sender) sender.replaceTrack(track);
      });
      if (localVideo.current) localVideo.current.srcObject = stream;
      track.onended = () => {
        const cameraTrack = localStream.current?.getVideoTracks()[0];
        Object.values(peers.current).forEach((pc) => {
          const sender = pc.getSenders().find((s) => s.track?.kind === "video");
          if (sender && cameraTrack) sender.replaceTrack(cameraTrack);
        });
        if (localVideo.current) localVideo.current.srcObject = localStream.current;
        screenStream.current = null;
        setSharing(false);
      };
      setSharing(true);
    } catch (e) { setError("Partage d'écran indisponible : " + e.message); }
  }

  async function handleDownload(file) {
    try { await downloadSharedFile(file.id, file.name); }
    catch (e) { setError(e.message); }
  }

  async function handleFile(e) {
    const file = e.target.files?.[0];
    if (!file || !room) return;
    try {
      const result = await shareFile(room.id, file);
      setFiles((old) => [...old, { ...result, size: file.size, sender: "Vous" }]);
    } catch (err) { setError(err.message); }
    e.target.value = "";
  }

  async function handleInvite(e) {
    e.preventDefault();
    try {
      await inviteRoom(room.id, inviteEmail);
      setInviteEmail("");
      setError("Invitation enregistrée.");
    } catch (err) { setError(err.message); }
  }

  async function moderate(id, action) {
    try {
      await removeParticipant(room.id, id, action);
      setParticipants((old) => old.filter((p) => String(p.user_id) !== String(id)));
    } catch (e) { setError(e.message); }
  }

  async function copyInvite() {
    await navigator.clipboard?.writeText(`${window.location.origin}/room-live?room=${room.id}`);
    setError("Lien de salle copié. L'accès reste soumis à l'invitation et à l'authentification.");
  }

  return (
    <main className="room-live-page">
      <header className="room-live-heading">
        <div><span className="room-live-eyebrow">BENJEDDOU ERP</span><h1>Room Live</h1>
          <p>{t("rl_subtitle")}</p></div>
        <button className="rl-secondary" onClick={refreshRooms}><RefreshCw size={16} /> {t("rl_refresh")}</button>
      </header>
      {error && <div className="rl-alert" role="status">{error}<button onClick={() => setError("")} aria-label="Fermer"><X size={16}/></button></div>}

      {!room ? (
        <div className="rl-lobby">
          <section className="rl-panel rl-create">
            <div className="rl-panel-title"><Plus size={19}/><h2>{t("rl_create")}</h2></div>
            <form onSubmit={handleCreate}>
              <label>{t("rl_name")}<input value={name} onChange={(e) => setName(e.target.value)} minLength={2} maxLength={100} required placeholder="Ex. Réunion équipe commerciale"/></label>
              <label>{t("rl_description")}<textarea value={description} onChange={(e) => setDescription(e.target.value)} maxLength={500} placeholder="Objet de la réunion (facultatif)"/></label>
              <label className="rl-switch"><input type="checkbox" checked={isPrivate} onChange={(e) => setIsPrivate(e.target.checked)}/><Lock size={16}/> {t("rl_private")}</label>
              <button className="rl-primary" disabled={busy || name.trim().length < 2}>{t("rl_create_join")}</button>
            </form>
          </section>
          <section className="rl-panel rl-room-list">
            <div className="rl-panel-title"><Users size={19}/><h2>{t("rl_available")}</h2></div>
            {rooms.length === 0 ? <p className="rl-empty">{t("rl_empty")}</p> :
              rooms.map((item) => <article className="rl-room-card" key={item.id}>
                <div className="rl-room-icon">{item.is_private ? <Lock size={18}/> : <Globe size={18}/>}</div>
                <div className="rl-room-info"><strong>{item.name}</strong><span>{item.description || t("rl_no_description")} · {item.participant_count} participant(s)</span></div>
                <button className="rl-secondary" disabled={busy} onClick={() => connectRoom(item)}>{t("rl_join")}</button>
              </article>)}
          </section>
        </div>
      ) : (
        <div className="rl-workspace">
          <section className="rl-main-panel">
            <div className="rl-room-top"><div><span className="rl-live-dot"/> {t("rl_live")}<h2>{room.name}</h2><small>{room.description}</small></div>
              <button className="rl-secondary" onClick={copyInvite}><Copy size={15}/> {t("rl_copy")}</button></div>
            <div className="rl-video-grid">
              <div className="rl-video-tile rl-local-tile"><video ref={localVideo} autoPlay muted playsInline/><span>{t("rl_you")} {sharing ? "· Partage d'écran" : ""}</span></div>
              {Object.entries(remoteStreams).map(([id]) => <div className="rl-video-tile" key={id}>
                <video autoPlay playsInline ref={(el) => { remoteVideoRefs.current[id] = el; }}/>
                <span>{participants.find((p) => String(p.user_id) === id)?.email || "Participant"}</span>
              </div>)}
              {Object.keys(remoteStreams).length === 0 && <div className="rl-video-placeholder"><Users size={32}/><span>{t("rl_waiting")}</span></div>}
            </div>
            <div className="rl-controls">
              <button className={!audioOn ? "is-off" : ""} onClick={toggleAudio} title="Microphone">{audioOn ? <Mic/> : <MicOff/>}</button>
              <button className={!videoOn ? "is-off" : ""} onClick={toggleVideo} title="Caméra">{videoOn ? <Video/> : <VideoOff/>}</button>
              <button className={sharing ? "is-active" : ""} onClick={toggleScreen} title="Partager l'écran">{sharing ? <MonitorOff/> : <MonitorUp/>}</button>
              <button className="rl-hangup" onClick={exitRoom} title="Quitter la salle"><PhoneOff/></button>
            </div>
          </section>
          <aside className="rl-side-panel">
            <div className="rl-tabs">
              <button className={activeTab === "chat" ? "active" : ""} onClick={() => setActiveTab("chat")}><MessageCircle size={16}/> {t("rl_chat")}</button>
              <button className={activeTab === "people" ? "active" : ""} onClick={() => setActiveTab("people")}><Users size={16}/> {t("rl_people")} ({participants.length})</button>
              <button className={activeTab === "files" ? "active" : ""} onClick={() => setActiveTab("files")}><Paperclip size={16}/> {t("rl_files")}</button>
            </div>
            {activeTab === "chat" && <><div className="rl-chat-list">{chat.map((m) => <div className="rl-message" key={m.id}><strong>{m.sender || "Utilisateur"}</strong><p>{m.content}</p><time>{m.created_at ? new Date(m.created_at).toLocaleTimeString() : ""}</time></div>)}</div>
              <form className="rl-chat-form" onSubmit={sendChat}><input value={draft} onChange={(e) => setDraft(e.target.value)} placeholder={t("rl_write")} maxLength={4000}/><button aria-label="Envoyer"><Send size={17}/></button></form></>}
            {activeTab === "people" && <div className="rl-people">
              <form className="rl-invite-form" onSubmit={handleInvite}><input type="email" required value={inviteEmail} onChange={(e) => setInviteEmail(e.target.value)} placeholder="email@entreprise.com"/><button aria-label="Inviter"><UserPlus size={17}/></button></form>
              {participants.map((p) => <div className="rl-person" key={p.user_id}><span className="rl-avatar">{(p.email || "?")[0].toUpperCase()}</span><div><strong>{p.email}</strong><small>{p.role === "host" ? t("rl_host") : t("rl_member")}</small></div>
                {p.role !== "host" && <div className="rl-person-actions"><button title="Bloquer" onClick={() => moderate(p.user_id, "block")}><Ban size={15}/></button><button title="Retirer" onClick={() => moderate(p.user_id, "remove")}><X size={15}/></button></div>}</div>)}
            </div>}
            {activeTab === "files" && <div className="rl-files"><label className="rl-upload"><Paperclip size={17}/> {t("rl_share_file")}<input type="file" onChange={handleFile}/></label>
              {files.map((f, i) => <div className="rl-file" key={`${f.id}-${i}`}><Paperclip size={16}/><span>{f.name}</span><button type="button" onClick={() => handleDownload(f)} title={t("rl_download")}><Download size={16}/></button></div>)}</div>}
          </aside>
        </div>
      )}
      <p className="rl-note">{t("rl_temp_note")}</p>
    </main>
  );
}
