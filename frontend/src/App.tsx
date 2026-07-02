import { Route, Routes } from "react-router-dom";

import Dashboard from "@/pages/Dashboard";
import Landing from "@/pages/Landing";
import ProcessingView from "@/pages/ProcessingView";
import StartClaim from "@/pages/StartClaim";
import ClaimReview from "@/pages/claim/ClaimReview";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/start" element={<StartClaim />} />
      <Route path="/processing/:claimId" element={<ProcessingView />} />
      <Route path="/claims" element={<Dashboard />} />
      <Route path="/claims/:claimId" element={<ClaimReview />} />
    </Routes>
  );
}
