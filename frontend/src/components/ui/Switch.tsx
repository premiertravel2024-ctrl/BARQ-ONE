import './switch.css';

type Props = {
  checked: boolean;
  onChange: (value: boolean) => void;
  label: string;
  disabled?: boolean;
  showLabel?: boolean;
};

export function Switch({checked, onChange, label, disabled, showLabel}: Props) {
  const control = (
    <button type="button" role="switch" aria-checked={checked} aria-label={label}
      className="barq-toggle" disabled={disabled} onClick={() => onChange(!checked)}>
      <span className="barq-toggle-thumb" aria-hidden="true" />
    </button>
  );
  return showLabel ? <span className="barq-toggle-row">{control}<span>{label}</span></span> : control;
}
