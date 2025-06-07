#!/usr/bin/env node
const RaydiumService = require('./raydium_service');

async function main() {
    try {
        // Read input from stdin
        let input = '';
        process.stdin.setEncoding('utf-8');
        
        for await (const chunk of process.stdin) {
            input += chunk;
        }
        
        // Parse parameters
        const params = JSON.parse(input);
        
        // Execute service
        const service = new RaydiumService();
        const result = await service.addLiquidity(params);
        
        // Output result as JSON
        process.stdout.write(JSON.stringify(result) + '\n');
        
    } catch (error) {
        const errorMessage = error instanceof Error ? error.message : String(error);
        process.stderr.write(errorMessage + '\n');
        process.exit(1);
    }
}

main(); 