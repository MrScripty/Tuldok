# Tuldok guides

Start with the [root README](../README.md) for installation and the Data → Pipeline → Runs workflow. The guides below cover individual formats, optional runtimes and operational details.

## Installation, access and storage

- [Local PostgreSQL setup, legacy migration, backup and recovery](contracts/local-storage.md)
- [Explicit schema upgrades](contracts/workspace-storage.md)
- [Owner sessions and scoped actors](contracts/actors.md)
- [Agent operations and MCP](contracts/agent-operations.md)
- [Optional MCP observations and privacy](contracts/mcp-observer.md)
- [Project manifests and read-only inspection](contracts/projects.md)
- [External text project files and current milestone limits](contracts/project-files.md)
- [Project command line](contracts/project-cli.md)

## Pipelines and execution

- [Editable pipeline recipes](contracts/workspace-pipeline.md)
- [Runs and runtime setup](contracts/workspace-runs.md)
- [Image classification](contracts/workspace-image-training.md)
- [Text classification](contracts/workspace-text-training.md)
- [Audio-interval classification](contracts/workspace-audio-training.md)
- [Validation/export without training](contracts/workspace-export-runs.md)
- [External recipes and exact execution permissions](contracts/external-recipes.md)

## Spatial and scientific data

- [Static meshes](contracts/static-mesh.md)
- [Mesh-release validation](contracts/mesh-release-validation.md)
- [Point clouds](contracts/point-cloud-data.md)
- [Volumes](contracts/volume-data.md)
- [Scientific field sequences](contracts/scientific-fields.md)
- [Rheon producer adapter](../adapters/rheon/README.md)
- [Rheon CPU training](contracts/rheon-cpu-training.md)
- [Rheon evaluation](contracts/rheon-evaluation.md)

Each format has its own import, review and export boundaries. Data-integrity evidence does not establish scientific validity or broad third-party format compatibility.

## Optional model assistance

- [Pumas image-to-text consumer](contracts/pumas-image-to-text-consumer.md)
- [Text-classification proposal design and evidence](plans/text-classification-proposals/plan.md)
- [Preference pairs](plans/preference-pairs/plan.md)
- [Classification exports](plans/image-classification-export/plan.md)
- [Plain-text corpus exports](plans/text-corpus-export/plan.md)

Provider support depends on the selected service, model and advertised capability. Runtime, model-quality and fixture evidence are separate. Preserve human review and provenance when producing releases.

## Screenshots and deeper reading

- [Image workspace gallery](images/workspaces-m2/README.md)
- [Image, text and audio workspace captures](images/workspaces-combined-20261012/README.md)
- [Audio Pipeline and Runs](images/workspaces-audio-runs/README.md)
- [Historical dataset-workbench captures](images/README.md)
- [Dataset-workspace design and dated implementation evidence](plans/dataset-centered-workspaces/plan.md)
- [Training evaluation research](research/training-evaluation/README.md)


## Preserved detailed reference

- [Former README, 2026-10-15](reference/README-20261015.md): detailed book-corner controls, provider setup, workflow instructions and dated qualification records, retained as a source snapshot. Use current owning contracts when behavior changes.
