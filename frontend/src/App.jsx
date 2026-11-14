import { Navigate, Route, Routes } from "react-router-dom";
import { ROLES } from "./auth.jsx";
import Layout from "./components/Layout.jsx";
import ProtectedRoute from "./components/ProtectedRoute.jsx";
import Alerts from "./pages/Alerts.jsx";
import CentreDetail from "./pages/CentreDetail.jsx";
import Centres from "./pages/Centres.jsx";
import DocPage from "./pages/DocPage.jsx";
import Login from "./pages/Login.jsx";
import ManageCentre from "./pages/ManageCentre.jsx";
import NewCentre from "./pages/NewCentre.jsx";
import Overview from "./pages/Overview.jsx";
import Upload from "./pages/Upload.jsx";
import Users from "./pages/Users.jsx";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route element={<ProtectedRoute><Layout /></ProtectedRoute>}>
        <Route path="/" element={<Navigate to="/overview" replace />} />
        <Route path="/overview" element={<Overview />} />
        <Route path="/centres" element={<Centres />} />
        <Route path="/centres/new" element={<ProtectedRoute roles={[ROLES.SUPER]}><NewCentre /></ProtectedRoute>} />
        <Route path="/centres/:id" element={<CentreDetail />} />
        <Route path="/centres/:id/manage" element={<ProtectedRoute roles={[ROLES.SUPER]}><ManageCentre /></ProtectedRoute>} />
        <Route path="/analyse" element={<ProtectedRoute roles={[ROLES.SUPER, ROLES.OFFICER]}><Upload /></ProtectedRoute>} />
        <Route path="/alerts" element={<Alerts />} />
        <Route path="/accuracy" element={<DocPage name="accuracy" title="Accuracy report" />} />
        <Route path="/privacy" element={<DocPage name="privacy" title="Privacy note" />} />
        <Route path="/users" element={<ProtectedRoute roles={[ROLES.SUPER]}><Users /></ProtectedRoute>} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
