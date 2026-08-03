import { Button } from "./ui/button";

const NavigationBar = () => {
  return (
    <nav className="fixed top-0 left-0 w-full z-50 bg-transparent text-white py-6 px-8">
      <div className="max-w-7xl mx-auto flex items-center justify-between py-6 px-8">

        <div className="flex items-center">
          <img
            src="src/assets/logo.png"
            className="h-20 rounded flex items-center justify-center"
            alt="Logo"
          />
        </div>

        <div className="flex items-center gap-12">
          <a
            href="#home"
            className="hover:text-gray-300 transition-colors text-sm font-medium"
          >
            Home
          </a>
          <a
            href="#history"
            className="hover:text-gray-300 transition-colors text-sm font-medium"
          >
            History
          </a>
          <a
            href="#references"
            className="hover:text-gray-300 transition-colors text-sm font-medium"
          >
            References
          </a>
        </div>

        <Button
          variant="outline"
          className="border-2 border-white text-white hover:bg-white hover:text-black transition-all px-8 py-5 text-sm font-medium"
        >
          Ask AI BOT
        </Button>
      </div>
    </nav>
  );
};

export default NavigationBar;
