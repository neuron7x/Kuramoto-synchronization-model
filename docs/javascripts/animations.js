(function () {
  if (typeof window === "undefined" || typeof document === "undefined") {
    return;
  }

  const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const animatedNodes = Array.from(document.querySelectorAll("[data-animate]"));

  if (animatedNodes.length === 0) {
    return;
  }

  const reveal = (node) => node.classList.add("is-visible");

  if (prefersReducedMotion.matches) {
    animatedNodes.forEach(reveal);
    return;
  }

  const observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting) {
          reveal(entry.target);
          observer.unobserve(entry.target);
        }
      }
    },
    {
      threshold: 0.25,
      rootMargin: "0px 0px -10% 0px"
    }
  );

  animatedNodes.forEach((node, index) => {
    node.style.transitionDelay = `${Math.min(index * 60, 360)}ms`;
    observer.observe(node);
  });
})();
