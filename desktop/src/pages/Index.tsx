import HeaderBar from "@/components/HeaderBar";
import LiveWaveform from "@/components/LiveWaveform";
import NoiseRemovalPanel from "@/components/NoiseRemovalPanel";
import SoundCategorization from "@/components/SoundCategorization";
import FileImportExport from "@/components/FileImportExport";
import SettingsSidebar from "@/components/SettingsSidebar";

const Index = () => {
  return (
    <div className="flex flex-col h-screen overflow-hidden">
      <HeaderBar />
      <div className="flex flex-1 overflow-hidden">
        <main className="flex-1 overflow-y-auto p-5 space-y-4">
          <LiveWaveform />
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <NoiseRemovalPanel />
            <SoundCategorization />
          </div>
          <FileImportExport />
        </main>
        <SettingsSidebar />
      </div>
    </div>
  );
};

export default Index;
