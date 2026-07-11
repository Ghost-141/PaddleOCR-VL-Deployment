#!/usr/bin/env bash
set -euo pipefail

export HF_HUB_DISABLE_XET="1"
export HF_HUB_DOWNLOAD_TIMEOUT="900"
export HF_HUB_ETAG_TIMEOUT="300"

repository="PaddlePaddle/PP-DocLayoutV2"
revision="b73668227b14316a38f8b345d6b474e4f1f0b84d"
destination="/models/PP-DocLayoutV2"
attempts=10
workers=1

mkdir -p "${destination}"

for attempt in $(seq 1 "${attempts}"); do
    echo "Downloading ${repository}@${revision} (attempt ${attempt}/${attempts})"
    if hf download "${repository}" \
        --revision "${revision}" \
        --local-dir "${destination}" \
        --max-workers "${workers}"; then
        missing=0
        for filename in config.json inference.json inference.pdiparams inference.yml; do
            if [[ ! -f "${destination}/${filename}" ]]; then
                echo "Missing required model file: ${filename}" >&2
                missing=1
            fi
        done
        if [[ "${missing}" -eq 0 ]]; then
            echo "Layout model ready at ${destination}"
            exit 0
        fi
    fi

    if [[ "${attempt}" -lt "${attempts}" ]]; then
        delay=$((attempt * 10))
        if [[ "${delay}" -gt 60 ]]; then
            delay=60
        fi
        echo "Download incomplete; resuming in ${delay} seconds"
        sleep "${delay}"
    fi
done

echo "Model download failed after ${attempts} attempts" >&2
exit 1
