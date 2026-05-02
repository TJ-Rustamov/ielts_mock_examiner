import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { ThemeProvider } from "@/contexts/ThemeContext";
import Auth from "./pages/Auth";
import Dashboard from "./pages/Dashboard";
import Writing from "./pages/Writing";
import Speaking from "./pages/Speaking";
import SpeakingTest from "./pages/SpeakingTest";
import WritingEvaluation from "./pages/WritingEvaluation";
import TestSessionDetail from "./pages/TestSessionDetail";
import Settings from "./pages/Settings";
import Pricing from "./pages/Pricing";
import NotFound from "./pages/NotFound";
import AdminOverview from "./pages/admin/AdminOverview";
import WritingTopics from "./pages/admin/WritingTopics";
import UserManagement from "./pages/admin/UserManagement";
import AIConfiguration from "./pages/admin/AIConfiguration";
import SpeakingConfig from "./pages/admin/SpeakingConfig";
import SpeakingQuestions from "./pages/admin/SpeakingQuestions";
import { getPostAuthRedirectPath, isAdminUser, isAuthenticated } from "./lib/auth";

const queryClient = new QueryClient();

const RequireAuth = ({ children }: { children: JSX.Element }) => {
  if (!isAuthenticated()) {
    return <Navigate to="/auth" replace />;
  }
  return children;
};

const RequireAdmin = ({ children }: { children: JSX.Element }) => {
  if (!isAuthenticated()) {
    return <Navigate to="/auth" replace />;
  }
  if (!isAdminUser()) {
    return <Navigate to="/" replace />;
  }
  return children;
};

const AuthOnly = ({ children }: { children: JSX.Element }) => {
  if (isAuthenticated()) {
    return <Navigate to={getPostAuthRedirectPath()} replace />;
  }
  return children;
};

const App = () => (
  <QueryClientProvider client={queryClient}>
    <ThemeProvider>
      <TooltipProvider>
        <Toaster />
        <Sonner />
        <BrowserRouter>
          <Routes>
            <Route path="/auth" element={<AuthOnly><Auth /></AuthOnly>} />
            <Route path="/" element={<RequireAuth><Dashboard /></RequireAuth>} />
            <Route path="/writing" element={<RequireAuth><Writing /></RequireAuth>} />
            <Route path="/speaking" element={<RequireAuth><Speaking /></RequireAuth>} />
            <Route path="/speaking/test/:part" element={<RequireAuth><SpeakingTest /></RequireAuth>} />
            <Route path="/writing/evaluation/:id" element={<RequireAuth><WritingEvaluation /></RequireAuth>} />
            <Route path="/session/:id" element={<RequireAuth><TestSessionDetail /></RequireAuth>} />
            <Route path="/settings" element={<RequireAuth><Settings /></RequireAuth>} />
            <Route path="/pricing" element={<RequireAuth><Pricing /></RequireAuth>} />
            <Route path="/admin" element={<RequireAdmin><AdminOverview /></RequireAdmin>} />
            <Route path="/admin/writing-topics" element={<RequireAdmin><WritingTopics /></RequireAdmin>} />
            <Route path="/admin/users" element={<RequireAdmin><UserManagement /></RequireAdmin>} />
            <Route path="/admin/ai-config" element={<RequireAdmin><AIConfiguration /></RequireAdmin>} />
            <Route path="/admin/speaking-config" element={<RequireAdmin><SpeakingConfig /></RequireAdmin>} />
            <Route path="/admin/speaking-questions" element={<RequireAdmin><SpeakingQuestions /></RequireAdmin>} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </BrowserRouter>
      </TooltipProvider>
    </ThemeProvider>
  </QueryClientProvider>
);

export default App;
