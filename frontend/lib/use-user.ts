"use client";

import { useEffect, useState } from "react";

export function useUserId(): string | null {
  const [userId, setUserId] = useState<string | null>(null);
  useEffect(() => {
    setUserId(window.localStorage.getItem("alphapilot_user_id"));
  }, []);
  return userId;
}

export function setSession(userId: string, token: string) {
  window.localStorage.setItem("alphapilot_user_id", userId);
  window.localStorage.setItem("alphapilot_token", token);
}

export function clearSession() {
  window.localStorage.removeItem("alphapilot_user_id");
  window.localStorage.removeItem("alphapilot_token");
}
