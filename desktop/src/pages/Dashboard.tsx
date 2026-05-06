import { useDesktopUiSurface } from "@/contexts/DesktopUiSurfaceContext";
import DevDashboard from "./DevDashboard";
import UserDashboard from "./UserDashboard";

const Dashboard = () => {
  const { surface } = useDesktopUiSurface();

  return surface === "dev" ? <DevDashboard /> : <UserDashboard />;
};

export default Dashboard;
