export default defineNuxtRouteMiddleware(async () => {
  const auth = useMealieAuth();
  if (!auth.loggedIn.value) await auth.getSession();
  if (!auth.loggedIn.value) return navigateTo("/login");
});
