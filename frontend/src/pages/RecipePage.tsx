import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Plus, Save } from 'lucide-react';
import { useEffect, useState } from 'react';
import { api } from '../api/client';
import type { RecipeLimitRow } from '../types';

interface RecipePageProps {
  machineId: number;
}

interface DraftLimit {
  tag_id: number;
  min_value: string;
  max_value: string;
  is_enabled: boolean;
}

function numOrNull(value: string): number | null {
  if (value.trim() === '') return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function RecipePage({ machineId }: RecipePageProps) {
  const queryClient = useQueryClient();
  const [selectedRecipeId, setSelectedRecipeId] = useState<number | null>(null);
  const [selectedSectionKey, setSelectedSectionKey] = useState<string | null>(null);
  const [draftLimits, setDraftLimits] = useState<Record<number, DraftLimit>>({});

  const recipesQuery = useQuery({ queryKey: ['recipes', machineId], queryFn: () => api.listRecipes(machineId) });
  const sectionsQuery = useQuery({ queryKey: ['sections', machineId], queryFn: () => api.getSections(machineId, true) });
  const limitsQuery = useQuery({
    queryKey: ['recipe-limits', selectedRecipeId, selectedSectionKey],
    queryFn: () => api.getRecipeLimits(selectedRecipeId as number, selectedSectionKey as string),
    enabled: Boolean(selectedRecipeId && selectedSectionKey)
  });

  const createRecipe = useMutation({
    mutationFn: () => {
      const recipeName = window.prompt('Recipe name:');
      if (!recipeName) throw new Error('Recipe name is required');
      const recipeCode = window.prompt('Optional recipe/job code:', '') || undefined;
      return api.createRecipe(machineId, { recipe_name: recipeName, recipe_code: recipeCode });
    },
    onSuccess: (recipe) => {
      setSelectedRecipeId(recipe.recipe_id);
      queryClient.invalidateQueries({ queryKey: ['recipes', machineId] });
    }
  });

  const setActiveRecipe = useMutation({
    mutationFn: (recipeId: number | null) => api.setActiveRecipe(machineId, recipeId, 'manual'),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['active-recipe', machineId] });
      queryClient.invalidateQueries({ queryKey: ['dashboard', machineId] });
    }
  });

  const saveLimits = useMutation({
    mutationFn: () => {
      if (!selectedRecipeId) throw new Error('No recipe selected');
      const limits = Object.values(draftLimits).map((item) => ({
        tag_id: item.tag_id,
        min_value: numOrNull(item.min_value),
        max_value: numOrNull(item.max_value),
        is_enabled: item.is_enabled
      }));
      return api.updateRecipeLimits(selectedRecipeId, limits);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['recipe-limits', selectedRecipeId, selectedSectionKey] });
      queryClient.invalidateQueries({ queryKey: ['dashboard', machineId] });
    }
  });

  const updateTagConfig = useMutation({
    mutationFn: ({ tagId, visible }: { tagId: number; visible: boolean }) => api.updateTagConfig(machineId, tagId, { is_visible: visible }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['recipe-limits', selectedRecipeId, selectedSectionKey] });
      queryClient.invalidateQueries({ queryKey: ['section-live'] });
    }
  });

  const rows = limitsQuery.data?.limits ?? [];
  const shownRows = rows.filter((row) => Boolean(row.is_visible));
  const hiddenRows = rows.filter((row) => !Boolean(row.is_visible));

  useEffect(() => {
    const next: Record<number, DraftLimit> = {};
    rows.forEach((row) => {
      next[row.tag_id] = {
        tag_id: row.tag_id,
        min_value: row.min_value === null || row.min_value === undefined ? '' : String(row.min_value),
        max_value: row.max_value === null || row.max_value === undefined ? '' : String(row.max_value),
        is_enabled: Boolean(row.is_limit_enabled)
      };
    });
    setDraftLimits(next);
  }, [rows.map((row) => `${row.tag_id}:${row.min_value}:${row.max_value}:${row.is_limit_enabled}`).join('|')]);

  function updateDraft(row: RecipeLimitRow, patch: Partial<DraftLimit>) {
    setDraftLimits((prev) => {
      const base: DraftLimit = prev[row.tag_id] ?? {
        tag_id: row.tag_id,
        min_value: row.min_value === null || row.min_value === undefined ? '' : String(row.min_value),
        max_value: row.max_value === null || row.max_value === undefined ? '' : String(row.max_value),
        is_enabled: Boolean(row.is_limit_enabled)
      };
      return {
        ...prev,
        [row.tag_id]: { ...base, ...patch, tag_id: row.tag_id }
      };
    });
  }

  function LimitTable({ data, hidden }: { data: RecipeLimitRow[]; hidden?: boolean }) {
    return (
      <div className="value-table-wrap recipe-table-wrap">
        <table className="value-table recipe-table">
          <thead>
            <tr>
              <th>Display Name</th>
              <th>Current</th>
              <th>Min</th>
              <th>Max</th>
              <th>Limit On</th>
              <th>Visible</th>
            </tr>
          </thead>
          <tbody>
            {data.map((row) => {
              const draft = draftLimits[row.tag_id] ?? {
                tag_id: row.tag_id,
                min_value: row.min_value === null || row.min_value === undefined ? '' : String(row.min_value),
                max_value: row.max_value === null || row.max_value === undefined ? '' : String(row.max_value),
                is_enabled: Boolean(row.is_limit_enabled)
              };
              return (
                <tr key={row.tag_id}>
                  <td>{row.label}</td>
                  <td className="current-value">{row.current_value}</td>
                  <td><input value={draft.min_value} onChange={(event) => updateDraft(row, { min_value: event.target.value })} /></td>
                  <td><input value={draft.max_value} onChange={(event) => updateDraft(row, { max_value: event.target.value })} /></td>
                  <td><input type="checkbox" checked={draft.is_enabled} onChange={(event) => updateDraft(row, { is_enabled: event.target.checked })} /></td>
                  <td><input type="checkbox" checked={!hidden} onChange={(event) => updateTagConfig.mutate({ tagId: row.tag_id, visible: event.target.checked })} /></td>
                </tr>
              );
            })}
            {!data.length && (
              <tr><td colSpan={6} className="muted-cell">No variables in this group.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    );
  }

  return (
    <div className="page recipe-page">
      <header className="page-header">
        <div>
          <h1>Recipes / Min-Max Limits</h1>
          <p>Create recipe limits for numeric values. These limits drive green/red section status and persistent alerts.</p>
        </div>
        <div className="header-actions">
          <button className="primary-button" onClick={() => createRecipe.mutate()}><Plus size={16} /> New Recipe</button>
          <button className="secondary-button" disabled={!selectedRecipeId} onClick={() => setActiveRecipe.mutate(selectedRecipeId)}>
            Load Selected Recipe
          </button>
        </div>
      </header>

      <div className="recipe-grid">
        <section className="panel-fill recipe-sidebar">
          <h2>Recipes</h2>
          <select value={selectedRecipeId ?? ''} onChange={(event) => setSelectedRecipeId(event.target.value ? Number(event.target.value) : null)}>
            <option value="">Select recipe</option>
            {recipesQuery.data?.map((recipe) => (
              <option key={recipe.recipe_id} value={recipe.recipe_id}>{recipe.recipe_name}</option>
            ))}
          </select>
          <h2>Sections</h2>
          <div className="section-scroll-list compact-list">
            {sectionsQuery.data?.filter((section) => Boolean(section.is_visible)).map((section) => (
              <button
                key={section.section_id}
                className={selectedSectionKey === section.section_key ? 'section-list-item active' : 'section-list-item'}
                onClick={() => setSelectedSectionKey(section.section_key)}
              >
                <span>{section.display_label}</span>
                <small>{section.limit_count} limits</small>
              </button>
            ))}
          </div>
        </section>

        <section className="panel-fill recipe-editor">
          <div className="panel-title-row">
            <div>
              <h2>{selectedSectionKey ?? 'Select a section'}</h2>
              <p>{selectedRecipeId ? 'Set min/max only for numeric values that matter.' : 'Select or create a recipe first.'}</p>
            </div>
            <button className="primary-button" disabled={!selectedRecipeId || !selectedSectionKey} onClick={() => saveLimits.mutate()}>
              <Save size={16} /> Save Limits
            </button>
          </div>

          {limitsQuery.isError && <div className="error-banner">{(limitsQuery.error as Error).message}</div>}
          {!selectedRecipeId || !selectedSectionKey ? (
            <div className="empty-state">Select a recipe and a section to edit limits.</div>
          ) : (
            <>
              <h3 className="subheading">Shown Variables</h3>
              <LimitTable data={shownRows} />
              <details className="hidden-vars">
                <summary>Hidden Variables ({hiddenRows.length})</summary>
                <LimitTable data={hiddenRows} hidden />
              </details>
            </>
          )}
        </section>
      </div>
    </div>
  );
}

export default RecipePage;
