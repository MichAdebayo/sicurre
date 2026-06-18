import { useEffect, useState } from "react";
import { motion, AnimatePresence, useAnimation } from "framer-motion";
import {
  Mail,
  Check,
  AlertTriangle,
  Lock,
  Cpu,
  RefreshCw,
} from "lucide-react";

const MotionDiv = motion.div as any;

interface Message {
  id: string;
  type: "legit" | "spam" | "phishing";
}

interface Particle {
  id: string;
  x: number;
  y: number;
  color: string;
}

const styleTag = `
  .perspective-container {
    perspective: 1400px;
    transform-style: preserve-3d;
  }
  .transform-style-3d {
    transform-style: preserve-3d;
  }
  
  /* 3D Email Envelope Cube rotation */
  @keyframes spinCube3D {
    0% { transform: rotateX(15deg) rotateY(0deg) rotateZ(-5deg); }
    50% { transform: rotateX(25deg) rotateY(180deg) rotateZ(5deg); }
    100% { transform: rotateX(15deg) rotateY(360deg) rotateZ(-5deg); }
  }
  .animate-cube-3d {
    animation: spinCube3D 6s linear infinite;
    transform-style: preserve-3d;
  }

  /* Mechanical Cog rotation */
  @keyframes rotateGear {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
  }
  .animate-gear-slow {
    animation: rotateGear 20s linear infinite;
  }

  /* Scanning Laser Sweep */
  @keyframes scanLaser {
    0%, 100% { top: 15%; opacity: 0.9; }
    50% { top: 85%; opacity: 0.9; }
  }
  .laser-beam {
    animation: scanLaser 1.8s ease-in-out infinite;
  }

  @keyframes pulseIndicator {
    0%, 100% { opacity: 0.4; transform: scale(0.95); }
    50% { opacity: 1; transform: scale(1.05); }
  }
  .animate-indicator {
    animation: pulseIndicator 1.2s infinite ease-in-out;
  }

  @keyframes flowDash {
    to { stroke-dashoffset: -40; }
  }
  .tube-flow {
    stroke-dasharray: 8 16;
    animation: flowDash 1.2s linear infinite;
  }

  /* Steel Bezel shadows */
  .steel-bezel {
    box-shadow: 
      inset 0 2px 3px rgba(255, 255, 255, 0.25),
      inset 0 -2px 3px rgba(0, 0, 0, 0.5),
      0 12px 24px rgba(0, 0, 0, 0.6);
  }

  /* Rivet styling */
  .rivet {
    width: 5px;
    height: 5px;
    background: radial-gradient(circle at 35% 35%, #cbd5e1 0%, #475569 80%, #020617 100%);
    border-radius: 50%;
    box-shadow: 1px 1px 2px rgba(0, 0, 0, 0.7);
  }

  /* Vent cooling slats */
  .vent-slats {
    background: repeating-linear-gradient(
      180deg,
      #020617 0px,
      #020617 4px,
      #1e293b 4px,
      #1e293b 6px
    );
  }
`;

// Specular 3D Mail Package
function EmailEnvelope3D({ color, shadow, type }: { color: string; shadow: string; type: string }) {
  // Determine envelope theme colors based on classification
  const getEnvelopeColors = () => {
    switch (type) {
      case "legit":
        return {
          paper: "bg-emerald-950/90 border-emerald-500/80",
          flap: "fill-emerald-800/85 stroke-emerald-500/40",
          back: "fill-emerald-900/90",
        };
      case "spam":
        return {
          paper: "bg-amber-950/90 border-amber-500/80",
          flap: "fill-amber-800/85 stroke-amber-500/40",
          back: "fill-amber-900/90",
        };
      case "phishing":
        return {
          paper: "bg-amber-950/90 border-[#D97706]",
          flap: "fill-amber-900/85 stroke-[#D97706]/40",
          back: "fill-amber-950/90",
        };
      default:
        return {
          paper: "bg-slate-900/95 border-blue-500/70",
          flap: "fill-slate-800/90 stroke-blue-500/30",
          back: "fill-slate-850/95",
        };
    }
  };

  const theme = getEnvelopeColors();

  return (
    <div className="relative w-9 h-7 animate-cube-3d transform-style-3d">
      {/* Front Face: Envelope Cover */}
      <div
        style={{ transform: "translateZ(3px)", boxShadow: `0 0 12px ${shadow}` }}
        className={`absolute inset-0 border rounded flex items-center justify-center ${theme.paper} transition-all duration-300`}
      >
        <svg className="absolute inset-0 w-full h-full" viewBox="0 0 36 28" fill="none">
          {/* Back pocket shape */}
          <path d="M 2 2 L 18 14 L 34 2" className={theme.flap} strokeWidth="1.5" />
          {/* Side folding triangles */}
          <path d="M 2 26 L 15 14" className="stroke-slate-600/40" strokeWidth="1" />
          <path d="M 34 26 L 21 14" className="stroke-slate-600/40" strokeWidth="1" />
        </svg>
        <Mail className="w-3.5 h-3.5 text-white/90 z-10" />
      </div>

      {/* Back Face */}
      <div
        style={{ transform: "rotateY(180deg) translateZ(3px)" }}
        className="absolute inset-0 bg-slate-950 border border-slate-800/40 rounded"
      />

      {/* Side Edges to give 3D Thickness */}
      <div
        style={{ transform: "rotateY(90deg) translateZ(18px) scaleY(0.78)" }}
        className="absolute inset-0 w-[6px] bg-slate-800 border-l border-slate-700/50"
      />
      <div
        style={{ transform: "rotateY(-90deg) translateZ(18px) scaleY(0.78)" }}
        className="absolute inset-0 w-[6px] bg-slate-800 border-r border-slate-700/50"
      />
    </div>
  );
}

// 3D Metallic Funnel Mouth (Intake Hopper)
function IndustrialFunnel3D() {
  return (
    <div
      style={{ transform: "rotateX(20deg) rotateY(15deg) translateZ(20px)", transformStyle: "preserve-3d" }}
      className="relative w-24 h-24 flex items-center justify-center"
    >
      {/* Cast Iron Bracket Plate (Base) */}
      <div className="absolute w-20 h-20 bg-gradient-to-br from-slate-900 to-slate-950 border border-slate-800 rounded-lg shadow-2xl flex items-center justify-center transform-style-3d">
        {/* Rivets at corners */}
        <div className="absolute top-1.5 left-1.5 rivet" />
        <div className="absolute top-1.5 right-1.5 rivet" />
        <div className="absolute bottom-1.5 left-1.5 rivet" />
        <div className="absolute bottom-1.5 right-1.5 rivet" />
      </div>

      {/* Tilted Funnel Body */}
      <div
        style={{ transform: "translateZ(15px)", transformStyle: "preserve-3d" }}
        className="w-18 h-18 rounded-full bg-gradient-to-r from-slate-700 via-slate-600 to-slate-950 flex items-center justify-center shadow-[inset_0_8px_16px_rgba(0,0,0,0.8),0_12px_28px_rgba(0,0,0,0.7)] border-[4px] border-slate-500/50 relative"
      >
        {/* Inside Deep Throat Glow */}
        <div className="absolute inset-2.5 rounded-full bg-slate-950 flex items-center justify-center shadow-inner overflow-hidden border border-slate-900">
          <div className="absolute inset-0 bg-gradient-to-b from-transparent to-blue-500/20 animate-pulse" />
          <RefreshCw className="w-6 h-6 text-blue-400/80 animate-spin" style={{ animationDuration: "12s" }} />
        </div>

        {/* Outer Bezel Rim Reflection */}
        <div className="absolute -inset-[3px] rounded-full border border-white/10 pointer-events-none" />
      </div>
    </div>
  );
}

// Hollow Industrial 3D Sorting Hopper (Tactile physical bin)
function HollowMetalBin3D({ color, icon: Icon, controls, label, glowColor }: { color: string; icon: any; controls: any; label: string; glowColor: string }) {
  return (
    <MotionDiv
      animate={controls}
      initial={{ scale: 1, rotateX: 22, rotateY: -15, z: 20 }}
      style={{ transformStyle: "preserve-3d" }}
      className="relative w-20 h-18 cursor-default group"
    >
      {/* 3D Side Walls (Right Panel) */}
      <div
        style={{
          transform: "rotateY(90deg) translateZ(40px) scaleX(0.7)",
          borderColor: `${color}40`,
        }}
        className="absolute inset-0 bg-slate-950 border rounded"
      />

      {/* 3D Side Walls (Left Panel) */}
      <div
        style={{
          transform: "rotateY(-90deg) translateZ(40px) scaleX(0.7)",
          borderColor: `${color}40`,
        }}
        className="absolute inset-0 bg-slate-950 border rounded"
      />

      {/* Back Wall - Deep Dark Inside */}
      <div
        style={{
          transform: "translateZ(-14px)",
          boxShadow: `inset 0 0 20px ${color}30`,
          borderColor: `${color}30`,
        }}
        className="absolute inset-0 bg-slate-950 border rounded flex flex-col justify-end p-1 pb-2 items-center"
      >
        <span className="text-[9px] font-bold tracking-wider opacity-90" style={{ color }}>
          {label}
        </span>
      </div>

      {/* Hollow Interior Glow Light Source */}
      <div
        className="absolute w-16 h-8 left-2 top-4 rounded-full filter blur-md pointer-events-none opacity-40 animate-pulse"
        style={{ backgroundColor: color, transform: "translateZ(-8px) rotateX(90deg)", boxShadow: `0 0 15px ${color}` }}
      />

      {/* Front Plate - Slanted steel plate with steel screen vent */}
      <div
        style={{
          transform: "translateZ(14px) rotateX(-2deg)",
          borderColor: color,
          borderWidth: "2px",
          boxShadow: `0 8px 25px rgba(0, 0, 0, 0.9), 0 0 15px ${color}30`,
        }}
        className="absolute inset-0 bg-gradient-to-b from-slate-900 via-slate-950 to-slate-950 rounded flex flex-col items-center justify-between p-2"
      >
        {/* Metal screen vent detail */}
        <div className="w-full h-4 rounded bg-slate-950/90 border border-slate-800 relative overflow-hidden flex items-center justify-center">
          <div className="absolute inset-0 vent-slats opacity-40" />
          <div className="absolute inset-0 bg-gradient-to-b from-transparent to-black/80" />
          {/* Glowing dot representing status */}
          <div className="w-1.5 h-1.5 rounded-full absolute" style={{ backgroundColor: color, boxShadow: `0 0 8px ${color}` }} />
        </div>

        {/* Central Beveled Icon Badge */}
        <div
          style={{
            backgroundColor: color,
            borderColor: `${color}80`,
            boxShadow: `0 2px 8px ${color}40`
          }}
          className="w-9 h-9 rounded-xl border flex items-center justify-center transition-transform duration-300 group-hover:scale-110"
        >
          <Icon className="w-5 h-5 text-slate-950 stroke-[2.5]" />
        </div>

        {/* Lower Steel Lip / Bezel */}
        <div className="w-[104%] h-1 bg-slate-950 border-t border-slate-800 rounded-full" />
      </div>

      {/* Top Rim collar line glow */}
      <div
        style={{ transform: "rotateX(90deg) translateZ(9px)", borderColor: color }}
        className="absolute inset-x-0 h-4 border-t-2 opacity-50 pointer-events-none"
      />
    </MotionDiv>
  );
}

// 3D Industrial Processor Console (Central Command Block)
function ConsoleMainframe3D({ scanning, scanType }: { scanning: boolean; scanType: "legit" | "spam" | "phishing" | null }) {
  return (
    <div
      style={{
        left: "50%",
        top: "50%",
        transform: "rotateX(15deg) rotateY(-18deg) rotateZ(0deg) translateZ(45px)",
        transformStyle: "preserve-3d",
      }}
      className="absolute -translate-x-1/2 -translate-y-1/2 z-20 w-36 h-44 flex items-center justify-center"
    >
      {/* 3D Right Side Wall with cooling grilles */}
      <div
        style={{ transform: "rotateY(90deg) translateZ(68px) scaleX(0.35)" }}
        className="absolute inset-y-0 w-32 bg-gradient-to-r from-slate-950 to-slate-900 border-r border-slate-800 vent-slats flex flex-col justify-around p-3"
      >
        <div className="h-1 bg-slate-950/90 rounded border-b border-white/5" />
        <div className="h-1 bg-slate-950/90 rounded border-b border-white/5" />
        <div className="h-1 bg-slate-950/90 rounded border-b border-white/5" />
      </div>

      {/* 3D Left Side Wall */}
      <div
        style={{ transform: "rotateY(-90deg) translateZ(68px) scaleX(0.35)" }}
        className="absolute inset-y-0 w-32 bg-gradient-to-l from-slate-950 to-slate-900 border-l border-slate-800 vent-slats"
      />

      {/* 3D Top Face */}
      <div
        style={{ transform: "rotateX(90deg) translateZ(86px) scaleY(0.35)" }}
        className="absolute inset-x-0 h-32 bg-gradient-to-b from-slate-700 to-slate-950 border-t border-slate-600 flex items-center justify-center"
      >
        {/* Large cooling fan vent cover */}
        <div className="w-16 h-16 rounded-full bg-slate-900 border border-slate-800 flex items-center justify-center shadow-inner relative overflow-hidden">
          <div className="absolute inset-0 vent-slats opacity-30 rotate-45" />
          <div className="w-6 h-6 rounded-full bg-slate-950 border border-slate-700 flex items-center justify-center">
            <div className="rivet" />
          </div>
        </div>
      </div>

      {/* Front Face: Steel Bezel and Glass Diagnostic Screen */}
      <div
        style={{ transform: "translateZ(18px)" }}
        className="absolute inset-0 rounded-2xl bg-gradient-to-b from-[#1B4FCC] via-[#1239A6] to-slate-950 border-[5px] border-[#1B4FCC]/60 steel-bezel relative overflow-hidden flex items-center justify-center"
      >
        {/* Corner Rivets */}
        <div className="absolute top-1.5 left-1.5 rivet" />
        <div className="absolute top-1.5 right-1.5 rivet" />
        <div className="absolute bottom-1.5 left-1.5 rivet" />
        <div className="absolute bottom-1.5 right-1.5 rivet" />

        {/* Screen Display Bezel Area */}
        <div className="w-[90%] h-[90%] rounded-xl bg-slate-950/90 backdrop-blur-sm border border-[#1B4FCC]/20 shadow-inner flex flex-col items-center justify-center relative overflow-hidden">
          {/* Glass Visor glare shine */}
          <div className="absolute inset-0 bg-gradient-to-br from-white/10 via-transparent to-transparent pointer-events-none z-20" />
          
          {/* Glowing scanning laser lines grid background */}
          <div className="absolute inset-0 bg-[linear-gradient(to_bottom,rgba(255,255,255,0.015)_1px,transparent_1px)] bg-[size:100%_4px] pointer-events-none" />

          {/* Internal rotating mechanical cogs inside display */}
          <div className="absolute w-24 h-24 flex items-center justify-center opacity-[0.12] pointer-events-none">
            <Cpu className="w-16 h-16 text-[#1B4FCC] animate-gear-slow" />
          </div>

          {/* Glowing diagnostics CPU core */}
          <div
            className={`w-16 h-16 rounded-full flex items-center justify-center border transition-all duration-300 z-10 ${
              scanning
                ? scanType === "legit"
                  ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400 shadow-[0_0_15px_rgba(16,185,129,0.15)]"
                  : scanType === "spam"
                  ? "bg-amber-500/10 border-amber-500/30 text-amber-400 shadow-[0_0_15px_rgba(245,158,11,0.15)]"
                  : "bg-[#D97706]/10 border-[#D97706]/30 text-[#D97706] shadow-[0_0_15px_rgba(217,119,6,0.15)]"
                : "bg-slate-950 border-[#1B4FCC]/30 text-[#1B4FCC]"
            }`}
          >
            <Cpu className="w-7 h-7" />
          </div>

          {/* Visual scan diagnostic grid sweep */}
          <AnimatePresence>
            {scanning && (
              <div
                className={`absolute left-0 right-0 h-[2px] opacity-90 laser-beam pointer-events-none z-30 ${
                  scanType === "legit"
                    ? "bg-emerald-400 shadow-[0_0_10px_#10b981,0_0_20px_#10b981]"
                    : scanType === "spam"
                    ? "bg-amber-400 shadow-[0_0_10px_#f59e0b,0_0_20px_#f59e0b]"
                    : "bg-[#D97706] shadow-[0_0_10px_#D97706,0_0_20px_#D97706]"
                }`}
              />
            )}
          </AnimatePresence>

          {/* Status Text overlay */}
          <div className="absolute bottom-2 inset-x-0 text-center select-none pointer-events-none">
            <span
              className={`text-[8px] font-mono tracking-widest uppercase transition-colors duration-200 ${
                scanning
                  ? scanType === "legit"
                    ? "text-emerald-400 animate-pulse"
                    : scanType === "spam"
                    ? "text-amber-400 animate-pulse"
                    : "text-[#D97706] animate-pulse"
                  : "text-slate-600"
              }`}
            >
              {scanning ? `SCANNING_${scanType}` : "SYS_IDLE"}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

function FlyingEmail({
  id,
  type,
  onScanBegin,
  onScanEnd,
  onArrived,
}: {
  id: string;
  type: "legit" | "spam" | "phishing";
  onScanBegin: () => void;
  onScanEnd: () => void;
  onArrived: () => void;
}) {
  const [stage, setStage] = useState<"intake" | "scanning" | "dispatching">("intake");

  useEffect(() => {
    const tScanBegin = setTimeout(() => {
      setStage("scanning");
      onScanBegin();
    }, 1000);

    const tScanEnd = setTimeout(() => {
      setStage("dispatching");
      onScanEnd();
    }, 2000);

    const tArrive = setTimeout(() => {
      onArrived();
    }, 3200);

    return () => {
      clearTimeout(tScanBegin);
      clearTimeout(tScanEnd);
      clearTimeout(tArrive);
    };
  }, [id, onScanBegin, onScanEnd, onArrived]);

  const getDestCoordinates = () => {
    switch (type) {
      case "legit":
        return { x: "85%", y: "22%" };
      case "spam":
        return { x: "85%", y: "50%" };
      case "phishing":
        return { x: "85%", y: "78%" };
    }
  };

  const dest = getDestCoordinates();

  const getGlowStyles = () => {
    if (stage === "intake") {
      return { color: "rgba(59, 130, 246, 0.6)", shadow: "rgba(59, 130, 246, 0.4)" };
    }
    if (stage === "scanning") {
      return { color: "rgba(255, 255, 255, 0.9)", shadow: "rgba(255, 255, 255, 0.6)" };
    }
    switch (type) {
      case "legit":
        return { color: "rgba(16, 185, 129, 0.8)", shadow: "rgba(16, 185, 129, 0.5)" };
      case "spam":
        return { color: "rgba(245, 158, 11, 0.8)", shadow: "rgba(245, 158, 11, 0.5)" };
      case "phishing":
        return { color: "rgba(217, 119, 6, 0.8)", shadow: "rgba(217, 119, 6, 0.6)" };
    }
  };

  const glows = getGlowStyles();

  // Dynamic 3D rotation angles mapping to trajectory curve to look realistic
  const getRotationTimeline = () => {
    if (stage === "intake") {
      return [0, 15, 0];
    }
    if (stage === "scanning") {
      return [0, 0, 0];
    }
    switch (type) {
      case "legit":
        return [0, -10, -25];
      case "spam":
        return [0, 0, 0];
      case "phishing":
        return [0, 10, 25];
    }
  };

  const rotY = getRotationTimeline();

  return (
    <MotionDiv
      initial={{ left: "15%", top: "50%", scale: 0, opacity: 0, z: 80, rotate: 0 }}
      animate={{
        left: ["15%", "50%", "50%", dest.x],
        top: ["50%", "50%", "50%", dest.y],
        z: [80, 180, 180, 20],
        scale: [0, 1.1, 1.25, 0.5],
        opacity: [0, 1, 1, 0],
        rotateX: [0, 15, 15, 45], // Dive down into hoppers
        rotateY: rotY,
      }}
      transition={{
        duration: 3.2,
        times: [0, 0.31, 0.62, 1],
        ease: "easeInOut",
      }}
      style={{ transformStyle: "preserve-3d" }}
      className="absolute w-9 h-7 -ml-4.5 -mt-3.5 z-40"
    >
      <EmailEnvelope3D color={glows.color} shadow={glows.shadow} type={stage === "dispatching" ? type : "normal"} />
    </MotionDiv>
  );
}

export function EmailGatewayAnimation() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [scanning, setScanning] = useState(false);
  const [scanType, setScanType] = useState<"legit" | "spam" | "phishing" | null>(null);
  const [particles, setParticles] = useState<Particle[]>([]);

  const basketLegitControls = useAnimation();
  const basketSpamControls = useAnimation();
  const basketPhishingControls = useAnimation();

  useEffect(() => {
    let count = 0;
    const interval = setInterval(() => {
      const r = Math.random();
      const type = r < 0.55 ? "legit" : r < 0.82 ? "spam" : "phishing";
      const id = `email-${count++}-${Date.now()}`;
      setMessages((prev) => [...prev, { id, type }]);
    }, 2400);

    return () => clearInterval(interval);
  }, []);

  const handleScanBegin = (type: "legit" | "spam" | "phishing") => {
    setScanning(true);
    setScanType(type);
  };

  const handleScanEnd = () => {
    setScanning(false);
    setScanType(null);
  };

  const spawnParticles = (type: "legit" | "spam" | "phishing") => {
    let color = "#10b981";
    let startY = 84; // Legit
    if (type === "spam") {
      color = "#f59e0b";
      startY = 190;
    } else if (type === "phishing") {
      color = "#D97706";
      startY = 296;
    }

    const newParticles: Particle[] = Array.from({ length: 6 }).map((_, i) => ({
      id: `p-${i}-${Date.now()}`,
      x: 510 + (Math.random() * 30 - 15),
      y: startY + (Math.random() * 10 - 5),
      color,
    }));

    setParticles((prev) => [...prev, ...newParticles]);

    // Clean up particles
    setTimeout(() => {
      setParticles((prev) => prev.filter((p) => !newParticles.find((np) => np.id === p.id)));
    }, 1200);
  };

  const handleArrived = async (id: string, type: "legit" | "spam" | "phishing") => {
    setMessages((prev) => prev.filter((m) => m.id !== id));
    spawnParticles(type);

    const bounceProps = {
      scale: [1, 1.28, 0.82, 1.08, 0.95, 1],
      rotateX: [22, 12, 32, 18, 24, 22],
      rotateY: [-15, -20, -10, -17, -13, -15],
      transition: { duration: 0.65, ease: "easeOut" },
    };

    if (type === "legit") {
      await basketLegitControls.start(bounceProps);
    } else if (type === "spam") {
      await basketSpamControls.start(bounceProps);
    } else {
      await basketPhishingControls.start(bounceProps);
    }
  };

  return (
    <div className="relative w-full h-[380px] max-w-[600px] bg-transparent overflow-hidden select-none perspective-container">
      <style>{styleTag}</style>

      {/* Atmospheric focal ambient light sources */}
      <div className="absolute top-1/2 left-[15%] -translate-y-1/2 w-32 h-32 bg-blue-500/5 blur-[50px] pointer-events-none" />
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-48 h-48 bg-indigo-500/5 blur-[55px] pointer-events-none" />
      <div className="absolute top-[22%] left-[85%] -translate-x-1/2 -translate-y-1/2 w-32 h-32 bg-emerald-500/5 blur-[40px] pointer-events-none" />
      <div className="absolute top-[50%] left-[85%] -translate-x-1/2 -translate-y-1/2 w-32 h-32 bg-amber-500/5 blur-[40px] pointer-events-none" />
      <div className="absolute top-[78%] left-[85%] -translate-x-1/2 -translate-y-1/2 w-32 h-32 bg-rose-500/5 blur-[40px] pointer-events-none" />

      {/* ── 3D Specular-Shaded Pneumatic Cylinders SVG Layer ── */}
      <svg className="absolute inset-0 w-full h-full pointer-events-none z-0">
        <defs>
          {/* Metallic polished steel pipe gradient */}
          <linearGradient id="chrome-pipe-body" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="#090d16" />
            <stop offset="20%" stopColor="#334155" />
            <stop offset="45%" stopColor="#e2e8f0" /> {/* Intense reflection shine */}
            <stop offset="55%" stopColor="#94a3b8" />
            <stop offset="80%" stopColor="#475569" />
            <stop offset="100%" stopColor="#020617" />
          </linearGradient>

          {/* Tilted pipe diagonal linear gradients */}
          <linearGradient id="chrome-pipe-diag-up" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#090d16" />
            <stop offset="25%" stopColor="#334155" />
            <stop offset="50%" stopColor="#f1f5f9" />
            <stop offset="75%" stopColor="#475569" />
            <stop offset="100%" stopColor="#020617" />
          </linearGradient>

          <linearGradient id="chrome-pipe-diag-down" x1="0%" y1="100%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#090d16" />
            <stop offset="25%" stopColor="#334155" />
            <stop offset="50%" stopColor="#f1f5f9" />
            <stop offset="75%" stopColor="#475569" />
            <stop offset="100%" stopColor="#020617" />
          </linearGradient>

          {/* Coupling clamp chrome finish */}
          <linearGradient id="joint-chrome" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#94a3b8" />
            <stop offset="50%" stopColor="#f8fafc" />
            <stop offset="100%" stopColor="#334155" />
          </linearGradient>

          {/* Pipe dropshadow filter */}
          <filter id="pipe-shadow" x="-10%" y="-10%" width="120%" height="120%">
            <feDropShadow dx="0" dy="12" stdDeviation="8" floodColor="#000000" floodOpacity="0.85" />
          </filter>
          <filter id="clamp-shadow" x="-20%" y="-20%" width="140%" height="140%">
            <feDropShadow dx="0" dy="4" stdDeviation="3" floodColor="#000" floodOpacity="0.9" />
          </filter>
        </defs>

        {/* ── Backing Shadows (Establishes depth on the background) ── */}
        <path d="M 90 190 L 300 190" stroke="#000" strokeWidth="36" fill="none" strokeLinecap="round" filter="url(#pipe-shadow)" />
        <path d="M 300 190 C 380 190, 420 84, 510 84" stroke="#000" strokeWidth="36" fill="none" strokeLinecap="round" filter="url(#pipe-shadow)" />
        <path d="M 300 190 L 510 190" stroke="#000" strokeWidth="36" fill="none" strokeLinecap="round" filter="url(#pipe-shadow)" />
        <path d="M 300 190 C 380 190, 420 296, 510 296" stroke="#000" strokeWidth="36" fill="none" strokeLinecap="round" filter="url(#pipe-shadow)" />

        {/* ── Outer Semi-Transparent Glass Pneumatic Jacket ── */}
        <path d="M 90 190 L 300 190" stroke="rgba(255, 255, 255, 0.15)" strokeWidth="32" fill="none" strokeLinecap="round" />
        <path d="M 300 190 C 380 190, 420 84, 510 84" stroke="rgba(255, 255, 255, 0.15)" strokeWidth="32" fill="none" strokeLinecap="round" />
        <path d="M 300 190 L 510 190" stroke="rgba(255, 255, 255, 0.15)" strokeWidth="32" fill="none" strokeLinecap="round" />
        <path d="M 300 190 C 380 190, 420 296, 510 296" stroke="rgba(255, 255, 255, 0.15)" strokeWidth="32" fill="none" strokeLinecap="round" />

        {/* Outer glass sleeve highlight borders */}
        <path d="M 90 190 L 300 190" stroke="rgba(255, 255, 255, 0.2)" strokeWidth="34" fill="none" strokeLinecap="round" strokeDasharray="30 150" />

        {/* ── Inner Polished Metallic Rail Guides ── */}
        {/* Left -> Central Command */}
        <path d="M 90 190 L 300 190" stroke="url(#chrome-pipe-body)" strokeWidth="18" fill="none" strokeLinecap="round" />
        <path d="M 90 190 L 300 190" stroke="#1B4FCC" strokeWidth="10" fill="none" strokeLinecap="round" />
        <path d="M 90 190 L 300 190" stroke="rgba(27, 79, 204, 0.6)" strokeWidth="2" strokeDasharray="6 18" fill="none" className="tube-flow" />

        {/* Central -> Legit Basket */}
        <path d="M 300 190 C 380 190, 420 84, 510 84" stroke="url(#chrome-pipe-diag-up)" strokeWidth="18" fill="none" strokeLinecap="round" />
        <path d="M 300 190 C 380 190, 420 84, 510 84" stroke="#1B4FCC" strokeWidth="10" fill="none" strokeLinecap="round" />
        <path d="M 300 190 C 380 190, 420 84, 510 84" stroke="rgba(16, 185, 129, 0.6)" strokeWidth="2" strokeDasharray="6 18" fill="none" className="tube-flow" />

        {/* Central -> Spam Basket */}
        <path d="M 300 190 L 510 190" stroke="url(#chrome-pipe-body)" strokeWidth="18" fill="none" strokeLinecap="round" />
        <path d="M 300 190 L 510 190" stroke="#1B4FCC" strokeWidth="10" fill="none" strokeLinecap="round" />
        <path d="M 300 190 L 510 190" stroke="rgba(245, 158, 11, 0.6)" strokeWidth="2" strokeDasharray="6 18" fill="none" className="tube-flow" />

        {/* Central -> Phishing Basket */}
        <path d="M 300 190 C 380 190, 420 296, 510 296" stroke="url(#chrome-pipe-diag-down)" strokeWidth="18" fill="none" strokeLinecap="round" />
        <path d="M 300 190 C 380 190, 420 296, 510 296" stroke="#1B4FCC" strokeWidth="10" fill="none" strokeLinecap="round" />
        <path d="M 300 190 C 380 190, 420 296, 510 296" stroke="rgba(217, 119, 6, 0.6)" strokeWidth="2" strokeDasharray="6 18" fill="none" className="tube-flow" />

        {/* ── Heavy Flanged Metal Coupler Joints (Anchor rings along pipes) ── */}
        {/* Intake coupler */}
        <rect x="120" y="176" width="10" height="28" rx="2" fill="url(#joint-chrome)" filter="url(#clamp-shadow)" />
        <circle cx="125" cy="181" r="1" fill="#000" />
        <circle cx="125" cy="199" r="1" fill="#000" />

        {/* Pre-mainframe coupler */}
        <rect x="248" y="176" width="10" height="28" rx="2" fill="url(#joint-chrome)" filter="url(#clamp-shadow)" />
        <circle cx="253" cy="181" r="1" fill="#000" />
        <circle cx="253" cy="199" r="1" fill="#000" />

        {/* Post-mainframe outgoing couplers */}
        <rect x="338" y="176" width="10" height="28" rx="2" fill="url(#joint-chrome)" filter="url(#clamp-shadow)" />
        
        {/* Legit output bend coupler */}
        <g transform="translate(450, 96) rotate(-22)">
          <rect x="-5" y="-14" width="10" height="28" rx="2" fill="url(#joint-chrome)" filter="url(#clamp-shadow)" />
        </g>

        {/* Phishing output bend coupler */}
        <g transform="translate(450, 282) rotate(22)">
          <rect x="-5" y="-14" width="10" height="28" rx="2" fill="url(#joint-chrome)" filter="url(#clamp-shadow)" />
        </g>
      </svg>

      {/* ── Left Intake: 3D Steel Funnel ── */}
      <div
        style={{ left: "15%", top: "50%", transform: "translateZ(30px)" }}
        className="absolute -translate-x-1/2 -translate-y-1/2 z-10 w-24 h-24 flex items-center justify-center"
      >
        <IndustrialFunnel3D />
      </div>

      {/* ── Center: 3D Mechanical Processor Console ── */}
      <ConsoleMainframe3D scanning={scanning} scanType={scanType} />

      {/* ── Right Column: 3D Hollow Metal Bins ── */}

      {/* 1. Legit Hopper (Top Right) */}
      <div
        style={{ left: "85%", top: "22%", transform: "translateZ(30px)", transformStyle: "preserve-3d" }}
        className="absolute -translate-x-1/2 -translate-y-1/2 z-10 w-20 h-20 flex items-center justify-center"
      >
        <HollowMetalBin3D
          color="#10b981"
          glowColor="rgba(16,185,129,0.3)"
          icon={Check}
          controls={basketLegitControls}
          label="LEGIT"
        />
      </div>

      {/* 2. Spam Hopper (Mid Right) */}
      <div
        style={{ left: "85%", top: "50%", transform: "translateZ(30px)", transformStyle: "preserve-3d" }}
        className="absolute -translate-x-1/2 -translate-y-1/2 z-10 w-20 h-20 flex items-center justify-center"
      >
        <HollowMetalBin3D
          color="#f59e0b"
          glowColor="rgba(245,158,11,0.3)"
          icon={AlertTriangle}
          controls={basketSpamControls}
          label="SPAM"
        />
      </div>

      {/* 3. Phishing/Quarantine Hopper (Bottom Right) */}
      <div
        style={{ left: "85%", top: "78%", transform: "translateZ(30px)", transformStyle: "preserve-3d" }}
        className="absolute -translate-x-1/2 -translate-y-1/2 z-10 w-20 h-20 flex items-center justify-center"
      >
        <HollowMetalBin3D
          color="#D97706"
          glowColor="rgba(217,119,6,0.3)"
          icon={Lock}
          controls={basketPhishingControls}
          label="PHISHING"
        />
      </div>

      {/* ── Active Flying Emails ── */}
      <AnimatePresence>
        {messages.map((m) => (
          <FlyingEmail
            key={m.id}
            id={m.id}
            type={m.type}
            onScanBegin={() => handleScanBegin(m.type)}
            onScanEnd={handleScanEnd}
            onArrived={() => handleArrived(m.id, m.type)}
          />
        ))}
      </AnimatePresence>

      {/* ── Floating Impact Particles ── */}
      <AnimatePresence>
        {particles.map((p) => (
          <MotionDiv
            key={p.id}
            initial={{ left: p.x, top: p.y, opacity: 1, scale: 1, z: 40 }}
            animate={{
              left: p.x + (Math.random() * 20 - 10),
              top: p.y - 45 - Math.random() * 20, // Float up
              opacity: 0,
              scale: 0.2,
            }}
            exit={{ opacity: 0 }}
            transition={{ duration: 1.0, ease: "easeOut" }}
            style={{
              backgroundColor: p.color,
              boxShadow: `0 0 6px ${p.color}`,
            }}
            className="absolute w-1.5 h-1.5 rounded-full pointer-events-none z-50"
          />
        ))}
      </AnimatePresence>
    </div>
  );
}
