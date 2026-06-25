import { useState } from 'react';
import type { Machine, Section } from '../types';

interface MachineMapProps {
  machine?: Machine;
  sections: Section[];
  selectedSectionKey: string | null;
  onSelect: (sectionKey: string) => void;
}

function MachineMap({ machine, sections, selectedSectionKey, onSelect }: MachineMapProps) {
  const [showBoxes, setShowBoxes] = useState(true);
  const visibleBoxes = sections.filter((section) => Boolean(section.is_visible) && section.has_box);

  return (
    <div className="machine-map-card panel-fill">
      <div className="panel-title-row">
        <div>
          <h2>Machine Map</h2>
          <p>Click a mapped section to load live values and last-hour history.</p>
        </div>
        <div className="map-header-actions">
          <button className="secondary-button small-button" onClick={() => setShowBoxes((current) => !current)}>
            {showBoxes ? 'Hide Boxes' : 'Show Boxes'}
          </button>
          <div className="map-legend">
            <span><i className="dot green" /> OK</span>
            <span><i className="dot red" /> Alert</span>
            <span><i className="dot orange" /> Returned</span>
            <span><i className="dot neutral" /> No Limits</span>
          </div>
        </div>
      </div>
      <div className="machine-image-wrap">
        {machine?.main_image_url ? (
          <img className="machine-image" src={machine.main_image_url} alt={machine.machine_name} />
        ) : (
          <div className="image-placeholder">No main machine image configured.</div>
        )}
        {showBoxes &&
          visibleBoxes.map((section) => (
            <button
              key={section.section_id}
              className={`map-box ${section.status} ${selectedSectionKey === section.section_key ? 'selected' : ''}`}
              style={{
                left: `${section.box_x_pct ?? 0}%`,
                top: `${section.box_y_pct ?? 0}%`,
                width: `${section.box_w_pct ?? 0}%`,
                height: `${section.box_h_pct ?? 0}%`
              }}
              title={section.display_label}
              onClick={() => onSelect(section.section_key)}
            >
              <span>{section.display_label}</span>
            </button>
          ))}
      </div>
    </div>
  );
}

export default MachineMap;
