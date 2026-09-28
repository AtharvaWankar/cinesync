const socket = io({
  reconnection: true,
  reconnectionAttempts: 10,
  reconnectionDelay: 1500,
  transports: ["polling", "websocket"],  // polling fallback prevents event burst on WS stall
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
