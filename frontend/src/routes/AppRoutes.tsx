import { BrowserRouter, Routes, Route } from "react-router-dom";
import NotFoundPage from "../pages/NotFoundPage";
import HomePage from "../pages/HomePage";
import LoginPage from "../pages/auth/LoginPage";
import RegisterPage from "../pages/auth/RegisterPage";
import UploadPage from "../pages/candidate/UploadPage";
import WorkspacePage from "../pages/candidate/WorkspacePage";
import DocumentsPage from "../pages/candidate/DocumentsPage";
import ProfilePage from "../pages/candidate/ProfilePage";
import FileDetailsPage from "../pages/candidate/FileDetailsPage";
import CandidateLayout from "../components/layout/CandidateLayout";
import StaffLayout from "../components/layout/StaffLayout";
import ReviewQueuePage from "../pages/staff/ReviewQueuePage";
import ReviewItemPage from "../pages/staff/ReviewItemPage";
import WorkspaceRedirect from "../components/layout/WorkspaceRedirect";
import AdminDocumentsPage from "../pages/staff/AdminDocumentsPage";
import AdminDocumentPage from "../pages/staff/AdminDocumentPage";
import AdminDashboardPage from "../pages/staff/AdminDashboardPage";
import AdminCandidatesPage from "../pages/staff/AdminCandidatesPage";
import AdminCandidatePage from "../pages/staff/AdminCandidatePage";
import StaffManagementPage from "../pages/staff/StaffManagementPage";

export default function AppRoutes() {
  return <BrowserRouter><Routes>
    <Route path="/" element={<HomePage />} />
    <Route path="/login" element={<LoginPage />} />
    <Route path="/register" element={<RegisterPage />} />
    <Route element={<CandidateLayout />}>
      <Route path="/workspace" element={<WorkspacePage />} />
      <Route path="/upload" element={<UploadPage />} />
      <Route path="/documents" element={<DocumentsPage />} />
      <Route path="/profile" element={<ProfilePage />} />
      <Route path="/files/:fileId" element={<FileDetailsPage />} />
    </Route>
    <Route element={<StaffLayout role="reviewer" />}>
      <Route path="/reviewer/reviews" element={<ReviewQueuePage />} />
      <Route path="/reviewer/reviews/:reviewId" element={<ReviewItemPage />} />
    </Route>
    <Route element={<StaffLayout role="administrator" />}>
      <Route path="/admin/staff" element={<StaffManagementPage />} />
      <Route path="/admin/dashboard" element={<AdminDashboardPage />} />
      <Route path="/admin/candidates" element={<AdminCandidatesPage />} />
      <Route path="/admin/candidates/:profileId" element={<AdminCandidatePage />} />
      <Route path="/admin/documents" element={<AdminDocumentsPage />} />
      <Route path="/admin/documents/:fileId" element={<AdminDocumentPage />} />
      <Route path="/admin/reviews" element={<ReviewQueuePage />} />
      <Route path="/admin/reviews/:reviewId" element={<ReviewItemPage />} />
    </Route>
    <Route path="/dashboard" element={<WorkspaceRedirect />} />
    <Route path="/admin" element={<WorkspaceRedirect />} />
    <Route path="/reviewer" element={<WorkspaceRedirect />} />
    <Route path="*" element={<NotFoundPage />} />
  </Routes></BrowserRouter>;
}
