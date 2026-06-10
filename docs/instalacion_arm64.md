# Instalación en macOS Apple Silicon (ARM64)

Todo el stack corre nativo en Apple Silicon vía conda-forge.

## 1. Crear el entorno

```bash
conda env create -f environment.yml
conda activate yaku
```

Esto instala `flopy`, `modflow6`, `pyemu`, `pestpp` (conda-forge), `modflow-setup`
(pip) y el propio paquete `yaku` en modo editable.

## 2. Verificar

```bash
yaku --version
python -c "import flopy, pyemu, mfsetup; print(flopy.__version__)"
which mf6 pestpp-glm pestpp-ies
```

Si falta el binario MODFLOW 6:

```bash
get-modflow :flopy
```

## 3. Probar end-to-end

```bash
yaku pipeline --project examples/caso_demo     # modelo + informe PDF
yaku calibrate --project examples/caso_demo --run --engine pestpp-glm
pytest -q                                      # suite de tests
```

## Notas ARM64

- `modflow-setup` se instala vía `pip` (no siempre está en conda-forge ARM64); ya
  está incluido en `environment.yml`.
- **MODPATH 7** no está disponible en conda-forge ARM64. Por eso las trayectorias
  (`yaku pathlines`) usan una aproximación por gradiente de Darcy (v = -K·∇h), no
  pathlines exactas ni tiempos de viaje. Para pathlines exactas, ejecutar MODPATH 7
  en Linux/x86 o vía Rosetta.
- `pestpp-glm` y `pestpp-ies` vienen por conda-forge y funcionan nativos.
