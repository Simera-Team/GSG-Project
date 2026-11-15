import { BrowserRouter, Navigate, Routes, Route } from "react-router-dom";
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
    <Route path="/dashboard" element={<Navigate to="/" replace />} />
    <Route path="*" element={<NotFoundPage />} />
  </Routes></BrowserRouter>;
}