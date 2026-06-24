import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Save, RefreshCcw } from 'lucide-react';
import { MouseEvent, useEffect, useMemo, useRef, useState } from 'react';
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
  const [savedBox, setSavedBox] = useState<DraftBox | null>(null);
  const [displayLabelDraft, setDisplayLabelDraft] = useState('');
  const [sectionPhotoPathDraft, setSectionPhotoPathDraft] = useState('');
  const [formError, setFormError] = useState<string | null>(null);

  const machineQuery = useQuery({ queryKey: ['machine', machineId], queryFn: () => api.getMachine(machineId) });
  const sectionsQuery = useQuery({ queryKey: ['sections', machineId], queryFn: () => api.getSections(machineId, true) });
  const syncMutation = useMutation({
    mutationFn: () => api.syncMachine(machineId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['sections', machineId] })
  });
  const updateSection = useMutation({
    mutationFn: ({ sectionId, payload }: { sectionId: number; payload: Partial<Section> }) => api.updateSection(sectionId, payload),
    onSuccess: () => {
      setFormError(null);
      queryClient.invalidateQueries({ queryKey: ['sections', machineId] });
      queryClient.invalidateQueries({ queryKey: ['dashboard', machineId] });
    },
    onError: (error: Error) => {
      setFormError(error.message);
    }
  });

  const sections = sectionsQuery.data ?? [];
  const selectedSection = useMemo(
    () => sections.find((section) => section.section_id === selectedSectionId) ?? sections[0],
    [sections, selectedSectionId]
  );

  useEffect(() => {
    if (!selectedSection) {
      setDraftBox(null);
      setSavedBox(null);
      return;
    }
    const nextBox =
      selectedSection.box_x_pct !== null &&
      selectedSection.box_x_pct !== undefined &&
      selectedSection.box_y_pct !== null &&
      selectedSection.box_y_pct !== undefined &&
      selectedSection.box_w_pct !== null &&
      selectedSection.box_w_pct !== undefined &&
      selectedSection.box_h_pct !== null &&
      selectedSection.box_h_pct !== undefined
        ? {
            x: Number(selectedSection.box_x_pct),
            y: Number(selectedSection.box_y_pct),
            w: Number(selectedSection.box_w_pct),
            h: Number(selectedSection.box_h_pct)
          }
        : null;
    setDraftBox(nextBox);
    setSavedBox(nextBox);
    setDisplayLabelDraft(selectedSection.display_label ?? '');
    setSectionPhotoPathDraft(selectedSection.section_photo_path ?? '');
    setFormError(null);
  }, [selectedSection]);

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
    if (draftBox.w < 1 || draftBox.h < 1) {
      setDraftBox(savedBox);
    }
    setDrawing(false);
    setDrawStart(null);
  }

  function saveDraftBox() {
    if (!selectedSection || !draftBox) return;
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
    setSavedBox(draftBox);
  }

  function saveSelectedField(payload: Partial<Section>) {
    if (!selectedSection) return;
    if (payload.display_label !== undefined) {
      const nextLabel = String(payload.display_label ?? '').trim();
      if (nextLabel) {
        const duplicate = sections.some(
          (section) =>
            section.section_id !== selectedSection.section_id &&
            section.display_label.trim().toLowerCase() === nextLabel.toLowerCase()
        );
        if (duplicate) {
          setFormError(`Display label "${nextLabel}" is already used by another section`);
          return;
        }
      }
      payload = { ...payload, display_label: nextLabel };
    }
    setFormError(null);
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
                <small>{section.has_box ? 'Mapped' : 'No box'}</small>
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
            {sections.filter((section) => Boolean(section.is_visible) && section.has_box).map((section) => {
              const box =
                selectedSection?.section_id === section.section_id && draftBox
                  ? draftBox
                  : {
                      x: Number(section.box_x_pct ?? 0),
                      y: Number(section.box_y_pct ?? 0),
                      w: Number(section.box_w_pct ?? 0),
                      h: Number(section.box_h_pct ?? 0)
                    };
              return (
              <button
                key={section.section_id}
                className={`map-box layout-box ${selectedSection?.section_id === section.section_id ? 'selected' : ''}`}
                style={{
                  left: `${box.x}%`,
                  top: `${box.y}%`,
                  width: `${box.w}%`,
                  height: `${box.h}%`
                }}
                onClick={(event) => {
                  event.stopPropagation();
                  setSelectedSectionId(section.section_id);
                }}
              >
                <span>{section.display_label}</span>
              </button>
              );
            })}
            {selectedSection && !selectedSection.has_box && draftBox && (
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
              {formError && <div className="error-banner">{formError}</div>}
              <label>
                Display Label
                <input
                  value={displayLabelDraft}
                  onChange={(event) => setDisplayLabelDraft(event.target.value)}
                  onBlur={() => saveSelectedField({ display_label: displayLabelDraft })}
                />
              </label>
              <label>
                Section Photo Path
                <input
                  value={sectionPhotoPathDraft}
                  placeholder="opc_photos/020 - Unwinder.jpeg"
                  onChange={(event) => setSectionPhotoPathDraft(event.target.value)}
                  onBlur={() => saveSelectedField({ section_photo_path: sectionPhotoPathDraft || null })}
                />
              </label>
              <div className="box-input-grid">
                <label>X %<input type="number" value={draftBox?.x ?? ''} onChange={(event) => setDraftBox((prev) => ({ x: event.target.value === '' ? 0 : Number(event.target.value), y: prev?.y ?? 0, w: prev?.w ?? 0, h: prev?.h ?? 0 }))} /></label>
                <label>Y %<input type="number" value={draftBox?.y ?? ''} onChange={(event) => setDraftBox((prev) => ({ x: prev?.x ?? 0, y: event.target.value === '' ? 0 : Number(event.target.value), w: prev?.w ?? 0, h: prev?.h ?? 0 }))} /></label>
                <label>W %<input type="number" value={draftBox?.w ?? ''} onChange={(event) => setDraftBox((prev) => ({ x: prev?.x ?? 0, y: prev?.y ?? 0, w: event.target.value === '' ? 0 : Number(event.target.value), h: prev?.h ?? 0 }))} /></label>
                <label>H %<input type="number" value={draftBox?.h ?? ''} onChange={(event) => setDraftBox((prev) => ({ x: prev?.x ?? 0, y: prev?.y ?? 0, w: prev?.w ?? 0, h: event.target.value === '' ? 0 : Number(event.target.value) }))} /></label>
              </div>
              <button className="primary-button" disabled={!draftBox || updateSection.isPending} onClick={saveDraftBox}><Save size={16} /> Save Box</button>
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
