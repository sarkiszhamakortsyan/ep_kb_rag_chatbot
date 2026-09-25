import { AdminPage } from "./features/admin/AdminPage";
import { ChatPage } from "./features/chat/ChatPage";

// Two screens don't justify a router dependency; nginx serves index.html for every path.
export default function App() {
  return window.location.pathname.startsWith("/admin") ? <AdminPage /> : <ChatPage />;
}
