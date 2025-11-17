#!/bin/bash
# Script to generate SVG diagrams from Mermaid files
# Usage: ./scripts/generate_conceptual_diagrams.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ASSETS_DIR="$PROJECT_ROOT/docs/architecture/assets"
PUPPETEER_CONFIG="$ASSETS_DIR/puppeteer-config.json"

echo "🎨 Generating conceptual architecture diagrams..."
echo "Project root: $PROJECT_ROOT"
echo "Assets directory: $ASSETS_DIR"

# Check if mermaid-cli is installed
if ! command -v mmdc &> /dev/null && ! npx --no-install -y @mermaid-js/mermaid-cli mmdc --version &> /dev/null; then
    echo "⚠️  Mermaid CLI not found. Installing @mermaid-js/mermaid-cli..."
    npm install -g @mermaid-js/mermaid-cli || {
        echo "❌ Failed to install mermaid-cli globally. Trying with npx..."
        MMDC_CMD="npx -y @mermaid-js/mermaid-cli mmdc"
    }
else
    if command -v mmdc &> /dev/null; then
        MMDC_CMD="mmdc"
    else
        MMDC_CMD="npx --no-install -y @mermaid-js/mermaid-cli mmdc"
    fi
fi

echo "Using Mermaid CLI: $MMDC_CMD"

# Function to generate SVG from Mermaid file
generate_svg() {
    local input_file="$1"
    local output_file="${input_file%.mmd}.svg"
    
    if [ ! -f "$input_file" ]; then
        echo "⚠️  File not found: $input_file"
        return 1
    fi
    
    echo "  📄 Processing: $(basename "$input_file")"
    
    if [ -f "$PUPPETEER_CONFIG" ]; then
        $MMDC_CMD -i "$input_file" -o "$output_file" -p "$PUPPETEER_CONFIG" -b transparent || {
            echo "  ❌ Failed to generate: $output_file"
            return 1
        }
    else
        $MMDC_CMD -i "$input_file" -o "$output_file" -b transparent || {
            echo "  ❌ Failed to generate: $output_file"
            return 1
        }
    fi
    
    echo "  ✅ Generated: $(basename "$output_file")"
}

# Generate SVGs for new conceptual diagrams
echo ""
echo "📊 Generating conceptual architecture diagrams..."

generate_svg "$ASSETS_DIR/conceptual_map.mmd"
generate_svg "$ASSETS_DIR/neuromodulation_system.mmd"
generate_svg "$ASSETS_DIR/tacl_system.mmd"
generate_svg "$ASSETS_DIR/signal_lifecycle.mmd"
generate_svg "$ASSETS_DIR/module_relationships.mmd"

# Regenerate existing diagrams if they exist
echo ""
echo "🔄 Regenerating existing diagrams..."

if [ -f "$ASSETS_DIR/system_overview.mmd" ]; then
    generate_svg "$ASSETS_DIR/system_overview.mmd"
fi

if [ -f "$ASSETS_DIR/data_flow.mmd" ]; then
    generate_svg "$ASSETS_DIR/data_flow.mmd"
fi

if [ -f "$ASSETS_DIR/service_interactions.mmd" ]; then
    generate_svg "$ASSETS_DIR/service_interactions.mmd"
fi

if [ -f "$ASSETS_DIR/feature_store_internals.mmd" ]; then
    generate_svg "$ASSETS_DIR/feature_store_internals.mmd"
fi

echo ""
echo "✅ All diagrams generated successfully!"
echo "📁 Output location: $ASSETS_DIR"
echo ""
echo "Generated files:"
ls -lh "$ASSETS_DIR"/*.svg | awk '{print "  - " $9 " (" $5 ")"}'

echo ""
echo "🎉 Done!"
