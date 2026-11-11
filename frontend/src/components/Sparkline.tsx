interface SparklineProps {
  values: number[];
  color: string;
}

export function Sparkline({ values, color }: SparklineProps) {
  if (values.length < 2) {
    return <div className="spark spark-empty">not enough samples</div>;
  }
  const width = 360;
  const height = 72;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const points = values
    .map((value, index) => {
      const x = (index / (values.length - 1)) * width;
      const y = height - 6 - ((value - min) / span) * (height - 12);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  return (
    <svg className="spark" viewBox={`0 0 ${width} ${height}`} role="img">
      <polyline fill="none" stroke={color} strokeWidth="2" points={points} />
    </svg>
  );
}
