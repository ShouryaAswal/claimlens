import { Navigate } from "react-router-dom";

/** "/" has no content of its own -- the Dashboard (now built, Day 3) is
 * the real entry point. Kept as a route (rather than pointing App.tsx's
 * "/" straight at Dashboard) so a bookmark to "/" still works even if
 * that changes later. */
export default function Landing() {
  return <Navigate to="/claims" replace />;
}
