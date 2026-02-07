import { Routes, Route } from "react-router-dom";
import WorldSelector from "./pages/WorldSelector.tsx";
import WorldView from "./pages/WorldView.tsx";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<WorldSelector />} />
      <Route path="/world/:worldId" element={<WorldView />} />
      <Route path="/world/:worldId/entity/:entityId" element={<WorldView />} />
    </Routes>
  );
}
