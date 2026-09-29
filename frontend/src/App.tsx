import { Navigate, Route, Routes } from "react-router-dom";
import type { ReactNode } from "react";
import Layout from "./components/Layout";
import { FullPageSpinner } from "./components/ui";
import { isStaffRole, useAuth } from "./lib/auth";
import AdminPage from "./pages/AdminPage";
import ComplaintDetailPage from "./pages/ComplaintDetailPage";
import CaseRoomPage from "./pages/CaseRoomPage";
import ComplaintsPage from "./pages/ComplaintsPage";
import DashboardPage from "./pages/DashboardPage";
import AdminDashboardPage from "./pages/AdminDashboardPage";
import DemoPage from "./pages/DemoPage";
import DocumentDetailPage from "./pages/DocumentDetailPage";
import DocumentsPage from "./pages/DocumentsPage";
import LoginPage from "./pages/LoginPage";
import SignupPage from "./pages/SignupPage";
import LandingPage from "./pages/LandingPage";
import FeaturesPage from "./pages/FeaturesPage";
import PoliciesPage from "./pages/PoliciesPage";
import HowItWorksPage from "./pages/HowItWorksPage";
import ManualReviewPage from "./pages/ManualReviewPage";
import RedTeamPage from "./pages/RedTeamPage";
import ReportsPage from "./pages/ReportsPage";
import RulesPage from "./pages/RulesPage";
import SecurityPage from "./pages/SecurityPage";
import CustomerHomePage from "./pages/CustomerHomePage";
import ChatHistoryPage from "./pages/ChatHistoryPage";
import ChatConversationPage from "./pages/ChatConversationPage";
import ProfilePage from "./pages/ProfilePage";
import CustomerServicesPage from "./pages/CustomerServicesPage";
import SimsPage from "./pages/SimsPage";
import PackagesPage from "./pages/PackagesPage";
import OrdersPage from "./pages/OrdersPage";
import TrackComplaintPage from "./pages/TrackComplaintPage";
import AdminUsersPage from "./pages/AdminUsersPage";
import AdminAgentsPage from "./pages/AdminAgentsPage";
import AdminDepartmentsPage from "./pages/AdminDepartmentsPage";
import AdminCategoriesPage from "./pages/AdminCategoriesPage";
import AdminAuditPage from "./pages/AdminAuditPage";
import AdminSettingsPage from "./pages/AdminSettingsPage";
import AgentDashboardPage from "./pages/AgentDashboardPage";
import AgentComplaintsPage from "./pages/AgentComplaintsPage";
import AgentCasePage from "./pages/AgentCasePage";

function StaffOnly({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  if (!isStaffRole(user?.role)) return <Navigate to="/" replace />;
  return <>{children}</>;
}

function AdminOnly({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  if (user?.role !== "admin") return <Navigate to="/" replace />;
  return <>{children}</>;
}

export default function App() {
  const { user, initializing } = useAuth();

  if (initializing) return <FullPageSpinner />;

  const isAdmin = user?.role === "admin";

  return (
    <Routes>
      <Route path="/features" element={<FeaturesPage />} />
      <Route path="/policies" element={<PoliciesPage />} />
      <Route path="/how-it-works" element={<HowItWorksPage />} />
      <Route path="/login" element={user ? <Navigate to="/" replace /> : <LoginPage />} />
      <Route path="/signup" element={user ? <Navigate to="/" replace /> : <SignupPage />} />

      <Route path="/" element={user ? <Layout /> : <LandingPage />}>
        {user && (
          <Route
            index
            element={
              isAdmin ? (
                <AdminDashboardPage />
              ) : user?.role === "reviewer" ? (
                <ManualReviewPage />
              ) : user?.role === "agent" ? (
                <AgentDashboardPage />
              ) : isStaffRole(user?.role) ? (
                <DashboardPage />
              ) : (
                <CustomerHomePage />
              )
            }
          />
        )}
      </Route>

      <Route element={user ? <Layout /> : <Navigate to="/login" replace />}>
        <Route path="complaints" element={<ComplaintsPage />} />
        <Route path="agent/complaints" element={user?.role === "agent" ? <AgentComplaintsPage /> : <Navigate to="/" replace />} />
        <Route path="agent/cases/:id" element={user?.role === "agent" ? <AgentCasePage /> : <Navigate to="/" replace />} />
        <Route
          path="chat-history"
          element={isStaffRole(user?.role) ? <Navigate to="/" replace /> : <ChatHistoryPage />}
        />
        <Route
          path="chat-history/:sessionId"
          element={isStaffRole(user?.role) ? <Navigate to="/" replace /> : <ChatConversationPage />}
        />
        <Route
          path="profile"
          element={isStaffRole(user?.role) ? <Navigate to="/" replace /> : <ProfilePage />}
        />
        <Route
          path="services"
          element={isStaffRole(user?.role) ? <Navigate to="/" replace /> : <CustomerServicesPage />}
        />
        <Route path="sims" element={<SimsPage />} />
        <Route
          path="packages"
          element={isStaffRole(user?.role) ? <Navigate to="/" replace /> : <PackagesPage />}
        />
        <Route path="orders" element={<OrdersPage />} />
        <Route path="complaints/:id" element={<ComplaintDetailPage />} />
        <Route
          path="track"
          element={isStaffRole(user?.role) ? <Navigate to="/complaints" replace /> : <TrackComplaintPage />}
        />
        <Route
          path="case-room/:id"
          element={
            <StaffOnly>
              <CaseRoomPage />
            </StaffOnly>
          }
        />
        <Route
          path="review"
          element={
            <StaffOnly>
              <ManualReviewPage />
            </StaffOnly>
          }
        />
        <Route
          path="lab"
          element={
            <StaffOnly>
              <RedTeamPage />
            </StaffOnly>
          }
        />
        <Route
          path="demo"
          element={
            <StaffOnly>
              <DemoPage />
            </StaffOnly>
          }
        />
        <Route
          path="documents"
          element={
            <StaffOnly>
              <DocumentsPage />
            </StaffOnly>
          }
        />
        <Route
          path="documents/:id"
          element={
            <StaffOnly>
              <DocumentDetailPage />
            </StaffOnly>
          }
        />
        <Route
          path="rules"
          element={
            <StaffOnly>
              <RulesPage />
            </StaffOnly>
          }
        />
        <Route
          path="reports"
          element={
            <StaffOnly>
              <ReportsPage />
            </StaffOnly>
          }
        />
        <Route
          path="security"
          element={
            <AdminOnly>
              <SecurityPage />
            </AdminOnly>
          }
        />

        {/* Admin-only dedicated sections */}
        <Route
          path="admin/users"
          element={
            <AdminOnly>
              <AdminUsersPage />
            </AdminOnly>
          }
        />
        <Route
          path="admin/agents"
          element={
            <AdminOnly>
              <AdminAgentsPage />
            </AdminOnly>
          }
        />
        <Route
          path="admin/departments"
          element={
            <AdminOnly>
              <AdminDepartmentsPage />
            </AdminOnly>
          }
        />
        <Route
          path="admin/categories"
          element={
            <AdminOnly>
              <AdminCategoriesPage />
            </AdminOnly>
          }
        />
        <Route
          path="admin/audit"
          element={
            <AdminOnly>
              <AdminAuditPage />
            </AdminOnly>
          }
        />
        <Route
          path="admin/settings"
          element={
            <AdminOnly>
              <AdminSettingsPage />
            </AdminOnly>
          }
        />
        <Route
          path="admin"
          element={
            <AdminOnly>
              <AdminPage />
            </AdminOnly>
          }
        />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
