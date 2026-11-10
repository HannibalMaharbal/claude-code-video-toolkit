export interface WordCaption {
  word: string;
  startMs: number;
  endMs: number;
}

export interface StatHighlight {
  value: string;
  label: string;
  subtitle?: string;
  trend?: 'up' | 'down' | 'neutral';
}

export interface KeyPoint {
  index: number;
  title: string;
  detail: string;
}

export interface CallToAction {
  headline: string;
  subline: string;
  badge: string;
  url?: string;
}

export interface B2BReelData {
  brandName: string;
  brandTagline?: string;
  badgeText: string;
  hookHeadline: string;
  hookSubline: string;
  statHighlight: StatHighlight;
  keyPoints: KeyPoint[];
  cta: CallToAction;
  captions?: WordCaption[];
  audioSrc?: string;
  fps: number;
  durationInSeconds: number;
}
