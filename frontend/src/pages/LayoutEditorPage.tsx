import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Save, RefreshCcw } from 'lucide-react';
import { MouseEvent, useMemo, useRef, useState } from 'react';
import { api } from '../api/client';
import type { Section } from '../types';

interface LayoutEditorPageProps {
  machineId: number;
}

interface DraftBox {
  x: number;
  y: number;
  w: number;
  h: number;
}

function roundPct(value: number) {
  return Math.max(0, Math.min(100, Number(value.toFixed(4))));
}

function LayoutEditorPage({ machineId }: LayoutEditorPageProps) {
  const queryClient = useQueryClient();
  const imageWrapRef = useRef<HTMLDivElement | null>(null);
  const [selectedSectionId, setSelectedSectionId] = useState<number | null>(null);
  const [drawing, setDrawing] = useState(false);
  const [drawStart, setDrawStart] = useState<{ x: number; y: number } | null>(null);
  const [draftBox, setDraftBox] = useState<DraftBox | null>(null);

  const machineQuery = useQuery({ queryKey: ['machine', machineId], queryFn: () => api.getMachine(machineId) });
  const sectionsQuery = useQuery({ queryKey: ['sections', machineId], queryFn: () => api.getSections(machineId, true) });
  const syncMutation = useMutation({
    mutationFn: () => api.syncMachine(machineId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['sections', machineId] })
  });
  const updateSection = useMutation({
    mutationFn: ({ sectionId, payload }: { sectionId: number; payload: Partial<Section> }) => api.updateSection(sectionId, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sections', machineId] });
      queryClient.invalidateQueries({ queryKey: ['dashboard', machineId] });
    }
  });

  const sections = sectionsQuery.data ?? [];
  const selectedSection = useMemo(
    () => sections.find((section) => section.section_id === selectedSectionId) ?? sections[0],
    [sections, selectedSectionId]
  );

  function getPct(event: MouseEvent<HTMLDivElement>) {
    const rect = imageWrapRef.current?.getBoundingClientRect();
    if (!rect) return { x: 0, y: 0 };
    return {
      x: roundPct(((event.clientX - rect.left) / rect.width) * 100),
      y: roundPct(((event.clientY - rect.top) / rect.height) * 100)
    };
  }

  function startDrawing(event: MouseEvent<HTMLDivElement>) {
    if (!drawing || !selectedSection) return;
    const point = getPct(event);
    setDrawStart(point);
    setDraftBox({ x: point.x, y: point.y, w: 0, h: 0 });
  }

  function moveDrawing(event: MouseEvent<HTMLDivElement>) {
    if (!drawing || !drawStart) return;
    const point = getPct(event);
    const x = Math.min(drawStart.x, point.x);
    const y = Math.min(drawStart.y, point.y);
    const w = Math.abs(point.x - drawStart.x);
    const h = Math.abs(point.y - drawStart.y);
    setDraftBox({ x: roundPct(x), y: roundPct(y), w: roundPct(w), h: roundPct(h) });
  }

  function stopDrawing() {
    if (!drawing || !draftBox || !selectedSection) return;
    if (draftBox.w >= 1 && draftBox.h >= 1) {
      updateSection.mutate({
        sectionId: selectedSection.section_id,
        payload: {
          box_x_pct: draftBox.x,
          box_y_pct: draftBox.y,
          box_w_pct: draftBox.w,
          box_h_pct: draftBox.h,
          is_visible: true
        }
      });
    }
    setDrawing(false);
    setDrawStart(null);
  }

  function saveSelectedField(payload: Partial<Section>) {
    if (!selectedSection) return;
    updateSection.mutate({ sectionId: selectedSection.section_id, payload });
  }

  return (
    <div className="page layout-page">
      <header className="page-header">
        <div>
          <h1>Machine Layout / Section Mapping</h1>
          <p>Draw persistent clickable boxes over the full machine image. Coordinates are saved as percentages.</p>
        </div>
        <div className="header-actions">
          <button className="secondary-button" onClick={() => syncMutation.mutate()}><RefreshCcw size={16} /> Sync Sections</button>
        </div>
      </header>

      <div className="layout-editor-grid">
        <section className="section-list panel-fill">
          <h2>Sections</h2>
          <div className="section-scroll-list">
            {sections.map((section) => (
              <button
                className={selectedSection?.section_id === section.section_id ? 'section-list-item active' : 'section-list-item'}
                key={section.section_id}
                onClick={() => setSelectedSectionId(section.section_id)}
              >
                <span>{section.display_label}</span>
                <small>{section.has_box ? 'Mapped' : 'No box'} | {Boolean(section.is_visible) ? 'Visible' : 'Hidden'}</small>
              </button>
            ))}
          </div>
        </section>

        <section className="layout-canvas panel-fill">
          <div className="panel-title-row">
            <div>
              <h2>{machineQuery.data?.machine_name ?? `Machine ${machineId}`}</h2>
              <p>Selected: {selectedSection?.display_label ?? 'None'}</p>
            </div>
            <button className={drawing ? 'danger-button' : 'primary-button'} onClick={() => setDrawing((prev) => !prev)}>
              {drawing ? 'Cancel Draw' : 'Draw / Replace Box'}
            </button>
          </div>
          <div
            className={drawing ? 'layout-image-wrap drawing' : 'layout-image-wrap'}
            ref={imageWrapRef}
            onMouseDown={startDrawing}
            onMouseMove={moveDrawing}
            onMouseUp={stopDrawing}
            onMouseLeave={stopDrawing}
          >
            {machineQuery.data?.main_image_url ? (
              <img className="machine-image" src={machineQuery.data.main_image_url} alt={machineQuery.data.machine_name} draggable={false} />
            ) : (
              <div className="image-placeholder">No main image configured in opc_machines.main_image_path.</div>
            )}
            {sections.filter((section) => Boolean(section.is_visible) && section.has_box).map((section) => (
              <button
                key={section.section_id}
                className={`map-box layout-box ${selectedSection?.section_id === section.section_id ? 'selected' : ''}`}
                style={{
                  left: `${section.box_x_pct ?? 0}%`,
                  top: `${section.box_y_pct ?? 0}%`,
                  width: `${section.box_w_pct ?? 0}%`,
                  height: `${section.box_h_pct ?? 0}%`
                }}
                onClick={(event) => {
                  event.stopPropagation();
                  setSelectedSectionId(section.section_id);
                }}
              >
                <span>{section.display_label}</span>
              </button>
            ))}
            {draftBox && (
              <div
                className="draft-box"
                style={{ left: `${draftBox.x}%`, top: `${draftBox.y}%`, width: `${draftBox.w}%`, height: `${draftBox.h}%` }}
              />
            )}
          </div>
        </section>

        <section className="section-editor panel-fill">
          <h2>Selected Section</h2>
          {selectedSection ? (
            <div className="form-stack">
              <label>
                Display Label
                <input
                  defaultValue={selectedSection.display_label}
                  onBlur={(event) => saveSelectedField({ display_label: event.target.value })}
                />
              </label>
              <label className="check-row strong">
                <input
                  type="checkbox"
                  checked={Boolean(selectedSection.is_visible)}
                  onChange={(event) => saveSelectedField({ is_visible: event.target.checked })}
                />
                Show this section on dashboard
              </label>
              <label>
                Sort Order
                <input
                  type="number"
                  defaultValue={selectedSection.sort_order}
                  onBlur={(event) => saveSelectedField({ sort_order: Number(event.target.value) })}
                />
              </label>
              <label>
                Section Photo Path
                <input
                  defaultValue={selectedSection.section_photo_path ?? ''}
                  placeholder="opc_photos/020 - Unwinder.jpeg"
                  onBlur={(event) => saveSelectedField({ section_photo_path: event.target.value || null })}
                />
              </label>
              <div className="box-input-grid">
                <label>X %<input type="number" value={selectedSection.box_x_pct ?? ''} onChange={(event) => saveSelectedField({ box_x_pct: event.target.value === '' ? null : Number(event.target.value) })} /></label>
                <label>Y %<input type="number" value={selectedSection.box_y_pct ?? ''} onChange={(event) => saveSelectedField({ box_y_pct: event.target.value === '' ? null : Number(event.target.value) })} /></label>
                <label>W %<input type="number" value={selectedSection.box_w_pct ?? ''} onChange={(event) => saveSelectedField({ box_w_pct: event.target.value === '' ? null : Number(event.target.value) })} /></label>
                <label>H %<input type="number" value={selectedSection.box_h_pct ?? ''} onChange={(event) => saveSelectedField({ box_h_pct: event.target.value === '' ? null : Number(event.target.value) })} /></label>
              </div>
              <button className="primary-button" onClick={() => selectedSection && saveSelectedField({})}><Save size={16} /> Saved Automatically</button>
            </div>
          ) : (
            <div className="empty-state">No sections found. Confirm opc_tags has active rows for this machine.</div>
          )}
        </section>
      </div>
    </div>
  );
}

export default LayoutEditorPage;
