import { AdminPage } from "../components/admin/admin-page";
import { RuntimeHealthPanel } from "../components/admin/runtime-health-panel";

export default function AdminOperationsRoute() {
  return (
    <AdminPage view="operations">
      <RuntimeHealthPanel />
    </AdminPage>
  );
}
