import React, { useState } from "react";
import { motion as Motion } from "framer-motion";
import { AlertCircle, Cake, LockKeyhole, Mail, Moon, Sun, UserRound } from "lucide-react";
import BorderGlow from "./BorderGlow";
import { darkModeGlowProps } from "./borderGlowTheme";
import { apiFetch } from "../utils/api";

export default function LoginPage({ theme, onToggleTheme, onLoginSuccess }) {
  const [mode, setMode] = useState("signin");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [signUpName, setSignUpName] = useState("");
  const [signUpEmail, setSignUpEmail] = useState("");
  const [signUpDob, setSignUpDob] = useState("");
  const [signUpPassword, setSignUpPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSignIn = async (event) => {
    event.preventDefault();
    setLoading(true);
    setError("");

    try {
      const response = await apiFetch("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ username, password }),
      });
      const result = await response.json();

      if (!response.ok || !result.success) {
        throw new Error(result.error || "Login failed");
      }

      onLoginSuccess(result.user);
    } catch (submitError) {
      setError(submitError.message || "Login failed");
    } finally {
      setLoading(false);
    }
  };

  const handleSignUp = async (event) => {
    event.preventDefault();
    setLoading(true);
    setError("");

    try {
      const response = await apiFetch("/api/auth/register", {
         method: "POST",
         body: JSON.stringify({
           name: signUpName,
           username: signUpName,   // ← added
           email: signUpEmail,
           dob: signUpDob,
            password: signUpPassword,
          }),
});
      
      const result = await response.json();

      if (!response.ok || !result.success) {
        throw new Error(result.error || "Sign up failed");
      }

      onLoginSuccess(result.user);
    } catch (submitError) {
      setError(submitError.message || "Sign up failed");
    } finally {
      setLoading(false);
    }
  };

  const loginCard = (
    <Motion.div
      className="w-full max-w-lg rounded-[2rem] border border-white/40 bg-white/95 p-6 shadow-xl backdrop-blur sm:p-7"
      initial={{ opacity: 0, y: 24 }}
      animate={{ opacity: 1, y: 0 }}
    >
        <div className="mb-5 rounded-[1.75rem] bg-blue-50 p-5">
          <div className="flex items-start justify-between gap-4">
          <div>
            <img
              src="/images/expense-tracker-sidebar-badge.svg"
              alt="Expense Tracker logo"
              className="h-14 w-auto max-w-[220px] object-contain"
            />
            <h1 className="mt-2 text-3xl font-bold">Sign in</h1>
            <p className="mt-2 text-sm text-gray-600">
              {mode === "signin"
                ? "Sign in with your username or email and password."
                : "Create a new account with your details."}
            </p>
          </div>
          <button
            type="button"
            className="rounded-full p-2 hover:bg-gray-100 transition"
            onClick={onToggleTheme}
            title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
          >
            {theme === "dark" ? <Sun size={20} /> : <Moon size={20} />}
          </button>
        </div>
        </div>

        <div className="mb-5 grid grid-cols-2 rounded-2xl bg-gray-100 p-1">
          <button
            type="button"
            className={`rounded-xl px-3 py-2 text-sm font-medium transition ${
              mode === "signin" ? "bg-white shadow" : "text-gray-600"
            }`}
            onClick={() => {
              setMode("signin");
              setError("");
            }}
          >
            Sign in
          </button>
          <button
            type="button"
            className={`rounded-xl px-3 py-2 text-sm font-medium transition ${
              mode === "signup" ? "bg-white shadow" : "text-gray-600"
            }`}
            onClick={() => {
              setMode("signup");
              setError("");
            }}
          >
            Sign up
          </button>
        </div>

        {mode === "signin" ? (
          <form className="space-y-4" onSubmit={handleSignIn}>
            <label className="block">
              <span className="mb-1 block text-sm font-medium">Username or Email</span>
              <div className="flex items-center gap-2 rounded-2xl border px-3 py-2.5">
                <UserRound size={18} className="text-gray-500" />
                <input
                  type="text"
                  value={username}
                  onChange={(event) => setUsername(event.target.value)}
                  placeholder="Username"
                  className="w-full border-0 bg-transparent p-0 focus:outline-none"
                  autoComplete="username"
                />
              </div>
            </label>

            <label className="block">
              <span className="mb-1 block text-sm font-medium">Password</span>
              <div className="flex items-center gap-2 rounded-2xl border px-3 py-2.5">
                <LockKeyhole size={18} className="text-gray-500" />
                <input
                  type="password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  placeholder="Password"
                  className="w-full border-0 bg-transparent p-0 focus:outline-none"
                  autoComplete="current-password"
                />
              </div>
            </label>

            {error ? (
              <div className="flex items-center gap-2 rounded-xl bg-red-50 px-3 py-3 text-sm text-red-600">
                <AlertCircle size={16} />
                <span>{error}</span>
              </div>
            ) : null}

            <button
              type="submit"
              disabled={loading}
              className="w-full rounded-2xl bg-blue-600 px-4 py-3 font-semibold text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {loading ? "Signing in..." : "Login"}
            </button>
          </form>
        ) : (
          <form className="space-y-4" onSubmit={handleSignUp}>
            <div className="grid gap-3 sm:grid-cols-2">
            <label className="block">
              <span className="mb-1 block text-sm font-medium">Name</span>
              <div className="flex items-center gap-2 rounded-2xl border px-3 py-2.5">
                <UserRound size={18} className="text-gray-500" />
                <input
                  type="text"
                  value={signUpName}
                  onChange={(event) => setSignUpName(event.target.value)}
                  placeholder="Full name"
                  className="w-full border-0 bg-transparent p-0 focus:outline-none"
                  autoComplete="name"
                />
              </div>
            </label>

            <label className="block">
              <span className="mb-1 block text-sm font-medium">Email</span>
              <div className="flex items-center gap-2 rounded-2xl border px-3 py-2.5">
                <Mail size={18} className="text-gray-500" />
                <input
                  type="email"
                  value={signUpEmail}
                  onChange={(event) => setSignUpEmail(event.target.value)}
                  placeholder="Email"
                  className="w-full border-0 bg-transparent p-0 focus:outline-none"
                  autoComplete="email"
                />
              </div>
            </label>

            <label className="block">
              <span className="mb-1 block text-sm font-medium">Date of Birth</span>
              <div className="flex items-center gap-2 rounded-2xl border px-3 py-2.5">
                <Cake size={18} className="text-gray-500" />
                <input
                  type="date"
                  value={signUpDob}
                  onChange={(event) => setSignUpDob(event.target.value)}
                  className="w-full border-0 bg-transparent p-0 focus:outline-none"
                />
              </div>
            </label>

            <label className="block">
              <span className="mb-1 block text-sm font-medium">Password</span>
              <div className="flex items-center gap-2 rounded-2xl border px-3 py-2.5">
                <LockKeyhole size={18} className="text-gray-500" />
                <input
                  type="password"
                  value={signUpPassword}
                  onChange={(event) => setSignUpPassword(event.target.value)}
                  placeholder="Password"
                  className="w-full border-0 bg-transparent p-0 focus:outline-none"
                  autoComplete="new-password"
                />
              </div>
            </label>
            </div>

            {error ? (
              <div className="flex items-center gap-2 rounded-xl bg-red-50 px-3 py-3 text-sm text-red-600">
                <AlertCircle size={16} />
                <span>{error}</span>
              </div>
            ) : null}

            <button
              type="submit"
              disabled={loading}
              className="w-full rounded-2xl bg-blue-600 px-4 py-3 font-semibold text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {loading ? "Creating account..." : "Create account"}
            </button>
          </form>
        )}
    </Motion.div>
  );

  return (
    <div
      className={`relative flex h-screen items-center justify-center overflow-hidden px-4 py-4 ${
        theme === "dark" ? "theme-dark" : "theme-light"
      }`}
      style={{
        backgroundImage: 'url("/images/image.png")',
        backgroundPosition: "center",
        backgroundRepeat: "no-repeat",
        backgroundSize: "cover",
      }}
    >
      <div
        className={`absolute inset-0 ${
          theme === "dark" ? "bg-slate-950/70" : "bg-white/55"
        }`}
      />
      {theme === "dark" ? (
        <div className="relative z-10">
          <BorderGlow {...darkModeGlowProps}>{loginCard}</BorderGlow>
        </div>
      ) : (
        <div className="relative z-10">{loginCard}</div>
      )}
    </div>
  );
}
