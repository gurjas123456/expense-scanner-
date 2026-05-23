import React, { useEffect, useState } from "react";
import { motion as Motion } from "framer-motion";
import { CheckCircle2, AlertCircle, LoaderCircle } from "lucide-react";
import { apiFetch } from "../utils/api";

export default function StatusIndicator() {
  const [status, setStatus] = useState("checking");

  async function checkBackendStatus() {
    try {
      const response = await apiFetch("/api/expenses");
      setStatus(response.ok ? "online" : "offline");
    } catch (error) {
      console.error("Backend status check failed:", error);
      setStatus("offline");
    }
  }

  useEffect(() => {
    const timerId = window.setTimeout(() => {
      checkBackendStatus();
    }, 0);

    const intervalId = window.setInterval(() => {
      checkBackendStatus();
    }, 30000);

    return () => {
      window.clearTimeout(timerId);
      window.clearInterval(intervalId);
    };
  }, []);

  if (status === "checking") {
    return (
      <Motion.span
        className="inline-flex items-center gap-1 rounded-full bg-gray-100 px-3 py-1 text-xs font-medium text-gray-600"
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
      >
        <LoaderCircle size={14} className="animate-spin" />
        Checking
      </Motion.span>
    );
  }

  if (status === "online") {
    return (
      <Motion.span
        className="inline-flex items-center gap-1 rounded-full bg-green-100 px-3 py-1 text-xs font-medium text-green-700"
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
      >
        <CheckCircle2 size={14} />
        Backend Online
      </Motion.span>
    );
  }

  return (
    <Motion.span
      className="inline-flex items-center gap-1 rounded-full bg-red-100 px-3 py-1 text-xs font-medium text-red-700"
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
    >
      <AlertCircle size={14} />
      Backend Offline
    </Motion.span>
  );
}
