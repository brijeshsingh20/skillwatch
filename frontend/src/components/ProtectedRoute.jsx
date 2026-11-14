import { Navigate, useLocation } from "react-router-dom";
import { ShieldX } from "lucide-react";
import { useAuth } from "../auth.jsx";
import { Spinner } from "./ui.jsx";

/** Redirects to /login when signed out; shows "not allowed" when the role isn't in `roles`. */
export default function ProtectedRoute({ roles, children }) {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <Spinner label="Checking your session…" />;
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  if (roles && !roles.includes(user.role)) {
    return (
      <div className="mx-auto mt-16 flex max-w-md items-center gap-3 rounded-lg border border-slate-200 bg-white p-6 text-slate-700">
        <ShieldX className="h-6 w-6 text-red-500" />
        <div>
          <div className="font-semibold">Not allowed</div>
          <div className="text-sm text-slate-500">Your role does not have access to this page.</div>
        </div>
      </div>
    );
  }
  return children;
}
