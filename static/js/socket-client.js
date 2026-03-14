/**
 * socket-client.js
 * Loaded on both host.html and watch.html.
 * Creates a global `socket` connected to the server.
 */

const socket = io({
  reconnection: true,
  reconnectionAttempts: 10,
  reconnectionDelay: 1500,
  transports: ["polling", "websocket"],
});

socket.on("connect", () => {
  console.log("[Socket] Connected:", socket.id);
});

socket.on("disconnect", (reason) => {
  console.warn("[Socket] Disconnected:", reason);
});

socket.on("connect_error", (err) => {
  console.error("[Socket] Connection error:", err.message);
});
