# Avisos y atribuciones de terceros

Este archivo identifica materiales y fuentes utilizados por FireWatch. No representa una licencia general para el código propio de FireWatch: esa decisión requiere aprobación de sus autores.

## Metodología y archivos instalados de BMAD

Las carpetas `.agents/skills/` y `_bmad/` incluyen archivos generados/instalados con **BMad Method v6.12.0**. Se conserva a continuación el aviso íntegro de su licencia MIT, incluido el aviso de marcas. Fuente: https://github.com/bmad-code-org/BMAD-METHOD/blob/V6.12/LICENSE

```text
MIT License

Copyright (c) 2025 BMad Code, LLC

This project incorporates contributions from the open source community.
See [CONTRIBUTORS.md](CONTRIBUTORS.md) for contributor attribution.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

TRADEMARK NOTICE:
BMad™, BMad Method™, and BMad Core™ are trademarks of BMad Code, LLC, covering all
casings and variations (including BMAD, bmad, BMadMethod, BMAD-METHOD, etc.). The use of
these trademarks in this software does not grant any rights to use the trademarks
for any other purpose. See [TRADEMARK.md](TRADEMARK.md) for detailed guidelines.
```

## Biblioteca científica cffdrs_py

El proyecto declara la dependencia `cffdrs` desde https://github.com/cffdrs/cffdrs_py en `pyproject.toml`. GitHub la identifica con licencia **GPL-2.0**. La relación entre esa dependencia y la licencia que se elija para el código propio debe revisarse antes de su distribución. No se incluye aquí ni se modifica el código fuente de esa biblioteca.

## Fuentes de datos científicos

- **Open-Meteo — Historical Weather API:** datos meteorológicos históricos (https://open-meteo.com/). El proveedor indica **CC BY 4.0** para los datos y solicita crédito, enlace a la licencia y declaración de transformaciones. FireWatch procesó datos meteorológicos para su dataset científico; el origen consta en `src/data/download_weather_provincial.py`. Licencia: https://creativecommons.org/licenses/by/4.0/
- **NASA FIRMS — Fire Information for Resource Management System:** datos satelitales de detección de focos de calor (https://firms.modaps.eosdis.nasa.gov/). Utilizar la cita oficial correspondiente al producto/sensor descargado y revisar las condiciones del archivo de origen.
- **Instituto Geográfico Nacional (Argentina):** geometrías de límites provinciales utilizadas en el procesamiento geográfico. Metadatos de la capa de provincias: https://www.ign.gob.ar/archivos/sig250/metadatos/provincias.pdf (atribución Creative Commons según esos metadatos). Confirmar la correspondencia exacta de la versión descargada.

## Distribución del snapshot y limitaciones

El snapshot científico, los datos originales y la auditoría histórica **no se incluyen** en el repositorio. Cualquier entrega adicional por ZIP requiere verificar la identificación exacta de las fuentes y conservar su atribución, además del manifiesto y la estructura del snapshot. Publicar el código no implica una autorización automática para redistribuir cualquier recurso de terceros.

## Otros paquetes

Las dependencias Python y npm se descargan a partir de `uv.lock` y `frontend/package-lock.json`; cada paquete mantiene su propia licencia. Este listado destaca fuentes y bibliotecas relevantes, pero no sustituye un inventario completo de licencias transitivas.
