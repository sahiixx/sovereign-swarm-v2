const API_BASE = "http://YOUR_PC_IP:18800"; // change to your machine IP

async function post(path, body) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function get(path) {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export const api = {
  status: () => get("/api/v1/status"),
  mission: (goal, userId = "mobile_user") => post("/api/v1/mission", { goal, user_id: userId }),
  chat: (message, history = [], userId = "mobile_user") => post("/api/v1/chat", { message, history, user_id: userId }),
  missions: (limit = 20) => get(`/api/v1/missions?limit=${limit}`),
};
