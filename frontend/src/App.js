import { useEffect } from "react";
import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { Toaster } from "sonner";
import "@/index.css";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import Landing from "@/pages/Landing";
import Register from "@/pages/Register";
import Login from "@/pages/Login";
import UserDashboard from "@/pages/UserDashboard";
import BankConnect from "@/pages/BankConnect";
import LoanApply from "@/pages/LoanApply";
import LoanApplyChat from "@/pages/LoanApplyChat";
import LoanResult from "@/pages/LoanResult";
import AdminDashboard from "@/pages/AdminDashboard";
import SecurityOverview from "@/pages/SecurityOverview";
import BankAssistant from "@/components/BankAssistant";

function Guard({ role, children }) {
  const { user, ready } = useAuth();
  const loc = useLocation();
  if (!ready) return <div className="min-h-screen flex items-center justify-center" data-testid="app-loading">Loading…</div>;
  if (!user) return <Navigate to="/login" replace state={{ from: loc.pathname }} />;
  if (role && user.role !== role) return <Navigate to={user.role === "admin" ? "/admin" : "/app"} replace />;
  return children;
}

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Toaster position="top-right" richColors />
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/security" element={<SecurityOverview />} />
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route path="/app" element={<Guard role="user"><UserDashboard /></Guard>} />
          <Route path="/app/bank" element={<Guard role="user"><BankConnect /></Guard>} />
          <Route path="/app/loan" element={<Guard role="user"><LoanApply /></Guard>} />
          <Route path="/app/loan/:id" element={<Guard role="user"><LoanResult /></Guard>} />
          <Route path="/app/loan/chat" element={<Guard role="user"><LoanApplyChat /></Guard>} />
          <Route path="/admin" element={<Guard role="admin"><AdminDashboard /></Guard>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        <BankAssistant />
      </AuthProvider>
    </BrowserRouter>
  );
}

export default App;