"use client";

/**
 * Checkbox-chip team selector. Replaces the old <select multiple>, whose
 * ctrl/cmd-click multi-select nobody discovers; visible checkboxes make
 * "pick any number" self-evident (and actually work on touch screens).
 */
export default function TeamPicker({
  options,
  selected,
  onChange,
  legend,
  clearLabel,
}: {
  options: string[];
  selected: string[];
  onChange: (teams: string[]) => void;
  legend: string;
  clearLabel: string;
}) {
  const toggle = (team: string, on: boolean) =>
    onChange(on ? [...selected, team] : selected.filter((t) => t !== team));

  return (
    <fieldset className="team-picker">
      <legend>{legend}</legend>
      <div className="team-picker-grid">
        {options.map((team) => (
          <label key={team} className={selected.includes(team) ? "team-chip on" : "team-chip"}>
            <input
              type="checkbox"
              checked={selected.includes(team)}
              onChange={(e) => toggle(team, e.target.checked)}
            />
            {team}
          </label>
        ))}
      </div>
      {selected.length > 0 && (
        <button type="button" className="team-picker-clear" onClick={() => onChange([])}>
          {clearLabel}
        </button>
      )}
    </fieldset>
  );
}
