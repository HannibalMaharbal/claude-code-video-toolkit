import React from 'react';
import { useCurrentFrame, useVideoConfig } from 'remotion';

export const AnimatedBackground: React.FC = () => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();

  // Seamless Loop Engineering: Full 2*PI oscillation guarantees frame 0 and final frame match
  const loopCycle = (frame / Math.max(1, durationInFrames)) * Math.PI * 2;
  const glowShift1 = Math.sin(loopCycle) * 30;
  const glowShift2 = Math.cos(loopCycle) * 40 - 40;

  return (
    <div
      style={{
        position: 'absolute',
        top: 0,
        left: 0,
        width: 1080,
        height: 1920,
        backgroundColor: '#07090E',
        overflow: 'hidden',
        zIndex: 0,
      }}
    >
      {/* Top subtle gold ambient glow */}
      <div
        style={{
          position: 'absolute',
          top: -200 + glowShift1,
          left: '50%',
          transform: 'translateX(-50%)',
          width: 900,
          height: 600,
          borderRadius: '50%',
          background: 'radial-gradient(circle, rgba(212,175,55,0.18) 0%, rgba(7,9,14,0) 70%)',
          filter: 'blur(80px)',
          pointerEvents: 'none',
        }}
      />

      {/* Bottom deep cobalt ambient glow */}
      <div
        style={{
          position: 'absolute',
          bottom: -250 + glowShift2,
          right: -100,
          width: 800,
          height: 700,
          borderRadius: '50%',
          background: 'radial-gradient(circle, rgba(30,58,138,0.22) 0%, rgba(7,9,14,0) 70%)',
          filter: 'blur(90px)',
          pointerEvents: 'none',
        }}
      />

      {/* Grid overlay for tech/consulting aesthetic */}
      <div
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          width: '100%',
          height: '100%',
          backgroundImage: `
            linear-gradient(rgba(255, 255, 255, 0.02) 1px, transparent 1px),
            linear-gradient(90deg, rgba(255, 255, 255, 0.02) 1px, transparent 1px)
          `,
          backgroundSize: '60px 60px',
          opacity: 0.6,
        }}
      />
    </div>
  );
};
