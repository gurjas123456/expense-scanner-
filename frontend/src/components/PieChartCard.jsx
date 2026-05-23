import React, { useEffect, useState } from "react";
import { motion as Motion } from "framer-motion";
import BorderGlow from "./BorderGlow";
import { darkModeGlowProps } from "./borderGlowTheme";
import { useTheme } from "./ThemeContext";
import { apiFetch } from "../utils/api";

const COLORS = ["#2563eb", "#059669", "#d97706", "#dc2626", "#7c3aed", "#0f766e"];

export default function PieChartCard() {
  const { theme } = useTheme();
  const [segments, setSegments] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function fetchExpenses() {
    setLoading(true);
    setError("");

    try {
      const response = await apiFetch("/api/expenses");
      const data = await response.json();

      if (!response.ok || !data.success) {
        throw new Error(data.error || "Failed to fetch expenses");
      }

      const totalsByCategory = (data.expenses || []).reduce((acc, expense) => {
        const key = expense.category || "Other";
        acc[key] = (acc[key] || 0) + Number(expense.amount || 0);
        return acc;
      }, {});

      const nextSegments = Object.entries(totalsByCategory)
        .sort((left, right) => right[1] - left[1])
        .map(([category, amount], index) => ({
          category,
          amount,
          color: COLORS[index % COLORS.length],
        }));

      setSegments(nextSegments);
    } catch (err) {
      console.error("Error fetching expense categories:", err);
      setError(err.message || "Failed to load category data");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    const timerId = window.setTimeout(() => {
      fetchExpenses();
    }, 0);

    const handleExpenseChange = () => {
      fetchExpenses();
    };

    window.addEventListener("expenseAdded", handleExpenseChange);
    window.addEventListener("expenseDeleted", handleExpenseChange);

    return () => {
      window.clearTimeout(timerId);
      window.removeEventListener("expenseAdded", handleExpenseChange);
      window.removeEventListener("expenseDeleted", handleExpenseChange);
    };
  }, []);

  const total = segments.reduce((sum, segment) => sum + segment.amount, 0);
  let cumulative = 0;

  const cardContent = (
    <Motion.div
      className="bg-white rounded-xl shadow p-6 flex flex-col gap-4"
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
    >
      <div>
        <h2 className="font-semibold">Category Breakdown</h2>
        <p className="text-sm text-gray-500">See where your spending is concentrated.</p>
      </div>

      {loading ? (
        <div className="flex items-center justify-center h-48 text-sm text-gray-500">Loading category data...</div>
      ) : error ? (
        <div className="flex items-center justify-center h-48 text-sm text-red-500">{error}</div>
      ) : segments.length === 0 ? (
        <div className="flex items-center justify-center h-48 text-sm text-gray-400">No expenses available yet.</div>
      ) : (
        <>
          <Motion.svg
            viewBox="0 0 120 120"
            className="mx-auto h-44 w-44 -rotate-90"
            initial={{ rotate: -180, opacity: 0 }}
            animate={{ rotate: 0, opacity: 1 }}
            transition={{ duration: 0.6 }}
          >
            {segments.map((segment) => {
              const fraction = segment.amount / total;
              const dash = fraction * 251.2;
              const gap = 251.2 - dash;
              const offset = -cumulative * 251.2;
              cumulative += fraction;

              return (
                <circle
                  key={segment.category}
                  cx="60"
                  cy="60"
                  r="40"
                  fill="transparent"
                  stroke={segment.color}
                  strokeWidth="18"
                  strokeDasharray={`${dash} ${gap}`}
                  strokeDashoffset={offset}
                />
              );
            })}
            <circle cx="60" cy="60" r="24" fill="white" />
            <text x="60" y="56" textAnchor="middle" className="fill-gray-500 text-[7px] rotate-90 origin-center">
              Total
            </text>
            <text x="60" y="66" textAnchor="middle" className="fill-gray-900 text-[8px] font-semibold rotate-90 origin-center">
              Rs.{total.toFixed(0)}
            </text>
          </Motion.svg>

          <div className="space-y-2">
            {segments.slice(0, 5).map((segment) => (
              <div key={segment.category} className="flex items-center justify-between text-sm">
                <div className="flex items-center gap-2">
                  <span className="h-3 w-3 rounded-full" style={{ backgroundColor: segment.color }}></span>
                  <span className="text-gray-700">{segment.category}</span>
                </div>
                <span className="font-medium text-gray-900">Rs.{segment.amount.toFixed(2)}</span>
              </div>
            ))}
          </div>
        </>
      )}
    </Motion.div>
  );

  return theme === "dark" ? (
    <BorderGlow {...darkModeGlowProps}>
      {cardContent}
    </BorderGlow>
  ) : (
    cardContent
  );
}
