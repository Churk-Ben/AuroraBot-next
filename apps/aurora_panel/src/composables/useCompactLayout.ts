import { onScopeDispose, ref } from 'vue';

export function useCompactLayout() {
  const query = window.matchMedia('(max-width: 900px)');
  const compact = ref(query.matches);
  const update = () => {
    compact.value = query.matches;
  };
  query.addEventListener('change', update);
  onScopeDispose(() => query.removeEventListener('change', update));
  return compact;
}
