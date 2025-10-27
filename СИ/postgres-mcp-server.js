#!/usr/bin/env node

const { Client } = require('pg');
const { Server } = require('@modelcontextprotocol/sdk/server/index.js');
const { StdioServerTransport } = require('@modelcontextprotocol/sdk/server/stdio.js');
const {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} = require('@modelcontextprotocol/sdk/types.js');

class PostgresMCPServer {
  constructor() {
    this.server = new Server(
      {
        name: 'postgres-mcp-server',
        version: '1.0.0',
      },
      {
        capabilities: {
          tools: {},
        },
      }
    );

    this.client = new Client({
      host: '192.168.1.139',
      port: 5432,
      database: 'equipment',
      user: 'postgres',
      password: '27915002'
    });

    this.setupHandlers();
  }

  setupHandlers() {
    this.server.setRequestHandler(ListToolsRequestSchema, async () => {
      return {
        tools: [
          {
            name: 'query_postgres',
            description: 'Execute a PostgreSQL query',
            inputSchema: {
              type: 'object',
              properties: {
                query: {
                  type: 'string',
                  description: 'SQL query to execute',
                },
              },
              required: ['query'],
            },
          },
          {
            name: 'get_equipment_count',
            description: 'Get total equipment count',
            inputSchema: {
              type: 'object',
              properties: {},
            },
          },
          {
            name: 'get_calibration_certificates_count',
            description: 'Get total calibration certificates count',
            inputSchema: {
              type: 'object',
              properties: {},
            },
          },
        ],
      };
    });

    this.server.setRequestHandler(CallToolRequestSchema, async (request) => {
      const { name, arguments: args } = request.params;

      const client = new Client({
        host: process.env.POSTGRES_HOST || '192.168.1.139',
        port: parseInt(process.env.POSTGRES_PORT) || 5432,
        database: process.env.POSTGRES_DATABASE || 'equipment',
        user: process.env.POSTGRES_USER || 'postgres',
        password: process.env.POSTGRES_PASSWORD || '27915002'
      });

      try {
        await client.connect();

        switch (name) {
          case 'query_postgres':
            const result = await client.query(args.query);
            return {
              content: [
                {
                  type: 'text',
                  text: JSON.stringify(result.rows, null, 2),
                },
              ],
            };

          case 'get_equipment_count':
            const equipmentResult = await client.query('SELECT COUNT(*) FROM equipment');
            return {
              content: [
                {
                  type: 'text',
                  text: `Total equipment: ${equipmentResult.rows[0].count}`,
                },
              ],
            };

          case 'get_calibration_certificates_count':
            const certResult = await client.query('SELECT COUNT(*) FROM calibration_certificates');
            return {
              content: [
                {
                  type: 'text',
                  text: `Total calibration certificates: ${certResult.rows[0].count}`,
                },
              ],
            };

          default:
            throw new Error(`Unknown tool: ${name}`);
        }
      } catch (error) {
        return {
          content: [
            {
              type: 'text',
              text: `Error: ${error.message}`,
            },
          ],
          isError: true,
        };
      } finally {
        await client.end();
      }
    });
  }

  async run() {
    const transport = new StdioServerTransport();
    await this.server.connect(transport);
    console.error('PostgreSQL MCP Server running on stdio');
  }
}

const server = new PostgresMCPServer();
server.run().catch(console.error);
