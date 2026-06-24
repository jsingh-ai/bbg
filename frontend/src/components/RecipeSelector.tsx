import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../api/client';

interface RecipeSelectorProps {
  machineId: number;
}

function RecipeSelector({ machineId }: RecipeSelectorProps) {
  const queryClient = useQueryClient();
  const recipesQuery = useQuery({ queryKey: ['recipes', machineId], queryFn: () => api.listRecipes(machineId) });
  const activeQuery = useQuery({ queryKey: ['active-recipe', machineId], queryFn: () => api.getActiveRecipe(machineId) });
  const setActive = useMutation({
    mutationFn: (recipeId: number | null) => api.setActiveRecipe(machineId, recipeId, 'manual'),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['active-recipe', machineId] });
      queryClient.invalidateQueries({ queryKey: ['dashboard', machineId] });
      queryClient.invalidateQueries({ queryKey: ['sections', machineId] });
    }
  });

  return (
    <div className="recipe-selector">
      <span>Recipe</span>
      <select
        value={activeQuery.data?.recipe_id ?? ''}
        onChange={(event) => setActive.mutate(event.target.value ? Number(event.target.value) : null)}
      >
        <option value="">No recipe selected</option>
        {recipesQuery.data?.filter((recipe) => Boolean(recipe.is_active)).map((recipe) => (
          <option value={recipe.recipe_id} key={recipe.recipe_id}>
            {recipe.recipe_name}{recipe.recipe_code ? ` (${recipe.recipe_code})` : ''}
          </option>
        ))}
      </select>
    </div>
  );
}

export default RecipeSelector;
