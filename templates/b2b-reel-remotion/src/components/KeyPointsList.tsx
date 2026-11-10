import React from 'react';
import { spring, useCurrentFrame, useVideoConfig } from 'remotion';
import { KeyPoint } from '../types';

interface KeyPointsListProps {
  points: KeyPoint[];
}

export const KeyPointsList: React.FC<KeyPointsListProps> = ({ points }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '24px',
        margin: '30px 60px 0 60px',
        zIndex: 2,
        boxSizing: 'border-box',
      }}
    >
      {points.map((pt, idx) => {
        const itemSpring = spring({
          frame: frame - (20 + idx * 8),
          fps,
          config: { damping: 14, stiffness: 110 },
        });

        return (
          <div
            key={pt.index}
            style={{
              transform: `translateY(${(1 - itemSpring) * 30}px) scale(${itemSpring})`,
              opacity: itemSpring,
              background: 'rgba(15, 23, 42, 0.75)',
              border: '1px solid rgba(255, 255, 255, 0.08)',
              borderRadius: '20px',
              padding: '24px 30px',
              display: 'flex',
              alignItems: 'flex-start',
              gap: '24px',
              backdropFilter: 'blur(12px)',
              boxShadow: '0 8px 24px rgba(0, 0, 0, 0.4)',
            }}
          >
            {/* Number Pill */}
            <div
              style={{
                width: '56px',
                height: '56px',
                borderRadius: '16px',
                backgroundColor: 'rgba(212, 175, 55, 0.15)',
                border: '1px solid #D4AF37',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                flexShrink: 0,
              }}
            >
              <span
                style={{
                  fontSize: '28px',
                  fontWeight: 900,
                  color: '#D4AF37',
                  fontFamily: 'system-ui, -apple-system, sans-serif',
                }}
              >
                {pt.index}
              </span>
            </div>

            {/* Content */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <div
                style={{
                  fontSize: '30px',
                  fontWeight: 800,
                  color: '#FFFFFF',
                  fontFamily: 'system-ui, -apple-system, sans-serif',
                }}
              >
                {pt.title}
              </div>
              <div
                style={{
                  fontSize: '22px',
                  fontWeight: 400,
                  color: '#94A3B8',
                  lineHeight: 1.35,
                  fontFamily: 'system-ui, -apple-system, sans-serif',
                }}
              >
                {pt.detail}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
};
