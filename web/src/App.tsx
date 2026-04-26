import { lazy, Suspense } from "react";
import { createBrowserRouter, Navigate, RouterProvider } from "react-router-dom";
import { QueryProvider } from "@/components/layout/query-provider";
import { Toaster } from "@/components/ui/toaster";
import Landing from "@/routes/landing";
import Login from "@/routes/login";

// Eager: Landing (the public marketing page Google sees) + Login (small +
// always on the critical path). Everything under /app is lazy-loaded so
// the public landing bundle doesn't ship the dashboard, sidebars, charts,
// and per-route UI just to render a static marketing page.
const AppShell = lazy(() =>
  import("@/components/layout/app-shell").then((m) => ({ default: m.AppShell })),
);
const Dashboard = lazy(() => import("@/routes/dashboard"));
const Courses = lazy(() => import("@/routes/courses"));
const CourseDetail = lazy(() => import("@/routes/course-detail"));
const Tasks = lazy(() => import("@/routes/tasks"));
const Deliverables = lazy(() => import("@/routes/deliverables"));
const Exams = lazy(() => import("@/routes/exams"));
const Files = lazy(() => import("@/routes/files"));
const Activity = lazy(() => import("@/routes/activity"));
const Settings = lazy(() => import("@/routes/settings"));

// Marketing landing is only for the hosted openstudy.dev deploy. Self-hosters
// leave VITE_SHOW_LANDING unset/false so `/` jumps straight to the app, same
// pattern Cal.com / n8n / Plausible / Ghost / Sentry use.
const SHOW_LANDING = import.meta.env.VITE_SHOW_LANDING === "true";

const router = createBrowserRouter([
  {
    path: "/",
    element: SHOW_LANDING ? <Landing /> : <Navigate to="/app" replace />,
  },
  { path: "/login", element: <Login /> },
  {
    path: "/app",
    element: <AppShell />,
    children: [
      { index: true, element: <Dashboard /> },
      { path: "courses", element: <Courses /> },
      { path: "courses/:code", element: <CourseDetail /> },
      { path: "tasks", element: <Tasks /> },
      { path: "deliverables", element: <Deliverables /> },
      { path: "exams", element: <Exams /> },
      { path: "files", element: <Files /> },
      { path: "activity", element: <Activity /> },
      { path: "settings", element: <Settings /> },
    ],
  },
]);

export default function App() {
  return (
    <QueryProvider>
      {/* Suspense catches the lazy-loaded /app routes while their chunks
          download. Fallback null = blank background tile briefly; users
          arriving at /app are usually authed already so the chunk is in
          cache. Could swap for a skeleton loader if cold-start UX needs it. */}
      <Suspense fallback={null}>
        <RouterProvider router={router} />
      </Suspense>
      <Toaster />
    </QueryProvider>
  );
}
