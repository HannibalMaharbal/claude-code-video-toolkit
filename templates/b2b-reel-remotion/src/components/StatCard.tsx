import React from 'react';
import { spring, useCurrentFrame, useVideoConfig } from 'remotion';
import { StatHighlight } from '../types';

interface StatCardProps {
  stat: StatHighlight;
}

export const StatCard: React.FC<StatCardProps> = ({ stat }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const cardScale = spring({
    frame: frame - 15,
    fps,
    config: { damping: 15, stiffness: 130 },
  });

  const valueGlow = Math.sin(frame / 12) * 0.15 + 0.85;

  return (
    <div
      style={{
        transform: `scale(${cardScale})`,
        opacity: cardScale,
        margin: '30px 60px 0 60px',
        background: 'linear-gradient(135deg, rgba(30, 41, 59, 0.75) 0%, rgba(15, 23, 42, 0.9) 100%)',
        border: '1.5px solid rgba(212, 175, 55, 0.5)',
        borderRadius: '24px',
        padding: '36px 44px',
        boxShadow: `0 16px 48px rgba(0, 0, 0, 0.6), 0 0 32px rgba(212, 175, 55, ${0.15 * valueGlow})`,
        backdropFilter: 'blur(16px)',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        textAlign: 'center',
        zIndex: 2,
        boxSizing: 'border-box',
      }}
    >
      <div
        style={{
          fontSize: '92px',
          fontWeight: 900,
          color: stat.trend === 'down' ? '#F87171' : '#34D399',
          letterSpacing: '-2px',
          lineHeight: 1,
          fontFamily: 'system-ui, -apple-system, sans-serif',
          textShadow: '0 0 30px rgba(248, 113, 113, 0.3)',
        }}
      >
        {stat.value}
      </div>

      <div
        style={{
          fontSize: '32px',
          fontWeight: 700,
          color: '#FFFFFF',
          marginTop: '16px',
          fontFamily: 'system-ui, -apple-system, sans-serif',
        }}
      >
        {stat.label}
      </div>

      {stat.subtitle && (
        <div
          style={{
            fontSize: '22px',
            fontWeight: 400,
            color: '#94A3B8',
            marginTop: '10px',
            fontFamily: 'system-ui, -apple-system, sans-serif',
          }}
        >
          {stat.subtitle}
        </div>
      )}
    </div>
  );
};
