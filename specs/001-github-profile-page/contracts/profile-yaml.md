# Contract: `profile.yaml`

See [data-model.md](../data-model.md) for field rules. Example:

```yaml
name: Roland Huß
intro: Engineer at Red Hat, co-author of "Kubernetes Patterns" and "Generative AI on Kubernetes", chili head.
links:
  - {label: Blog, url: https://ro14nd.de, emoji: "✍️"}
  - {label: LinkedIn, url: https://www.linkedin.com/in/ro14nd/, emoji: "💼"}
badges:
  - {label: Kubernetes, color: 326CE5, logo: kubernetes, logo_color: white}
main_projects:
  - repo: rhuss/cc-spex
    name: cc-spex
    emoji: "📐"
    description: >-
      Spec-driven development workflow for Claude Code. Brainstorm, specify, plan, and ship with review gates.
community:
  - {repo: jolokia/jolokia, name: Jolokia, role: creator, tagline: JMX on Capsaicin, HTTP/JSON bridge for JMX}
books:
  - {title: Kubernetes Patterns, url: https://k8spatterns.com, description: Reusable patterns for cloud-native apps, cover: assets/books/kubernetes-patterns.png}
more_tools:
  - {repo: rhuss/cc-cfp, tagline: Draft conference proposals with a simulated program committee}
settings:
  talks_shown: 8
```

Community `role` is one of `creator`, `co-creator`, `maintainer`, `alumni-maintainer`, `contributor`, `lead`. The README shows `alumni-maintainer` as "alumni maintainer" and every other role as written.

Unknown top-level keys are a validation error (catches typos).
