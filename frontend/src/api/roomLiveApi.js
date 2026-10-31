import { API_BASE_URL } from "./config";

function headers(extra = {}) {
  const token = localStorage.getItem("token");
  return { ...(token ? { Authorization: `Bearer ${token}` } : {}), ...extra };
}

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}/room-live${path}`, {
    ...options,
    headers: headers(options.headers || {}),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || data.message || `Erreur ${response.status}`);
  return data;
}

export const listRooms = () => request("/rooms");
export const createRoom = (payload) => request("/rooms", {
  method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
});
export const joinRoom = (id) => request(`/rooms/${id}/join`, { method: "POST" });
export const inviteRoom = (id, email) => request(`/rooms/${id}/invite`, {
  method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email }),
});
export const removeParticipant = (id, uid, action = "remove") => request(
  `/rooms/${id}/participants/${encodeURIComponent(uid)}/${action === "block" ? "block" : "remove"}`,
  { method: "POST" },
);
export const leaveRoom = (id) => request(`/rooms/${id}/leave`, { method: "POST" });

export async function shareFile(roomId, file) {
  const form = new FormData();
  form.append("file", file);
  return request(`/rooms/${roomId}/files`, { method: "POST", body: form });
}

export function roomWebSocketUrl(roomId) {
  const token = localStorage.getItem("token");
  const api = new URL(API_BASE_URL);
  const protocol = api.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${api.host}/api/room-live/ws/${roomId}?token=${encodeURIComponent(token || "")}`;
}

export async function downloadSharedFile(fileId, filename) {
  const response = await fetch(`${API_BASE_URL}/room-live/files/${encodeURIComponent(fileId)}`, {
    headers: headers(),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || `Erreur ${response.status}`);
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename || "document";
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
