import React, { useEffect, useState } from "react";
import Sidebar from "./components/Sidebar";
import Navbar from "./components/Navbar";
import Dashboard from "./components/Dashboard";
import UploadCard from "./components/UploadCard";
import Reports from "./components/Reports";
import Settings from "./components/Settings";
import LoginPage from "./components/LoginPage";
import { ThemeContext } from "./components/ThemeContext";
import { apiFetch } from "./utils/api";

export default function App() {
  const [page, setPage] = useState("Dashboard");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [user, setUser] = useState(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [theme, setTheme] = useState(() => {
    if (typeof window === "undefined") {
      return "light";
    }

    return window.localStorage.getItem("expense-tracker-theme") || "light";
  });

  useEffect(() => {
    document.body.classList.toggle("theme-light-body", theme === "light");
    document.body.classList.toggle("theme-dark-body", theme === "dark");
    window.localStorage.setItem("expense-tracker-theme", theme);

    return () => {
      document.body.classList.remove("theme-light-body");
      document.body.classList.remove("theme-dark-body");
    };
  }, [theme]);

  useEffect(() => {
    let active = true;

    const fetchSession = async () => {
      try {
        const response = await apiFetch("/api/auth/me", {
          method: "GET",
          headers: {},
        });

        if (!active) {
          return;
        }

        if (!response.ok) {
          setUser(null);
          return;
        }

        const result = await response.json();
        setUser(result.user || null);
      } catch {
        if (active) {
          setUser(null);
        }
      } finally {
        if (active) {
          setAuthLoading(false);
        }
      }
    };

    fetchSession();

    return () => {
      active = false;
    };
  }, []);

  const toggleTheme = () => {
    setTheme((currentTheme) => (currentTheme === "dark" ? "light" : "dark"));
  };

  const handlePageChange = (nextPage) => {
    setPage(nextPage);
    setSidebarOpen(false);
  };

  const handleLoginSuccess = (nextUser) => {
    setUser(nextUser);
    setPage("Dashboard");
  };

  const handleLogout = async () => {
    try {
      await apiFetch("/api/auth/logout", {
        method: "POST",
      });
    } catch {
      // Clear the local auth state even if the request fails.
    } finally {
      setUser(null);
      setPage("Dashboard");
      setSidebarOpen(false);
    }
  };

  let content;
  if (page === "Dashboard") content = <Dashboard />;
  else if (page === "Upload Receipt") content = <UploadCard />;
  else if (page === "Reports") content = <Reports />;
  else if (page === "Settings") {
    content = <Settings user={user} onLogout={handleLogout} />;
  }

  if (authLoading) {
    return (
      <div
        className={`flex min-h-screen items-center justify-center ${
          theme === "dark" ? "theme-dark" : "theme-light"
        }`}
      >
        <div className="rounded-2xl bg-white px-6 py-4 shadow">Checking session...</div>
      </div>
    );
  }

  if (!user) {
    return (
      <ThemeContext.Provider value={{ theme }}>
        <LoginPage
          theme={theme}
          onToggleTheme={toggleTheme}
          onLoginSuccess={handleLoginSuccess}
        />
      </ThemeContext.Provider>
    );
  }

  return (
    <ThemeContext.Provider value={{ theme }}>
      <div
        className={`app-shell flex min-h-screen bg-gray-50 ${
          theme === "dark" ? "theme-dark" : "theme-light"
        }`}
      >
        <Sidebar
          setPage={handlePageChange}
          activePage={page}
          isOpen={sidebarOpen}
          onClose={() => setSidebarOpen(false)}
        />
        <div className="flex min-w-0 flex-1 flex-col">
          <Navbar
            theme={theme}
            onToggleTheme={toggleTheme}
            onToggleSidebar={() => setSidebarOpen((current) => !current)}
            sidebarOpen={sidebarOpen}
            user={user}
            onOpenSettings={() => handlePageChange("Settings")}
            onLogout={handleLogout}
          />
          <main className={`flex-1 p-4 md:p-6 ${page === "Settings" ? "overflow-hidden" : "overflow-auto"}`}>
            {content}
          </main>
        </div>
      </div>
    </ThemeContext.Provider>
  );
}
