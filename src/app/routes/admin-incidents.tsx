import { AdminPage } from "../components/admin/admin-page";
import { OperationalExercisePanel } from "../components/admin/operational-exercise-panel";

export default function AdminIncidentsRoute() {
  return (
    <AdminPage view="incidents">
      <OperationalExercisePanel />
    </AdminPage>
  );
}
