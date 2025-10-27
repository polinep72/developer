const { Server } = require('@modelcontextprotocol/sdk/server/index.js');
const { StdioServerTransport } = require('@modelcontextprotocol/sdk/server/stdio.js');
const {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} = require('@modelcontextprotocol/sdk/types.js');
const { Client } = require('pg');

class MultiDatabasePostgreSQLServer {
  constructor() {
    this.server = new Server(
      {
        name: 'multi-postgres-mcp-server',
        version: '1.0.0',
      },
      {
        capabilities: {
          tools: {},
        },
      }
    );

    // Конфигурация баз данных
    this.databases = {
      equipment: {
        host: '192.168.1.139',
        port: 5432,
        database: 'equipment',
        user: 'postgres',
        password: '27915002'
      },
      // Добавьте другие БД здесь
      // another_db: {
      //   host: '192.168.1.139',
      //   port: 5432,
      //   database: 'another_db',
      //   user: 'postgres',
      //   password: '27915002'
      // }
    };

    this.setupToolHandlers();
  }

  setupToolHandlers() {
    this.server.setRequestHandler(ListToolsRequestSchema, async () => {
      return {
        tools: [
          {
            name: 'query_postgres',
            description: 'Executes a read-only SQL query on the specified PostgreSQL database.',
            inputSchema: {
              type: 'object',
              properties: {
                database: {
                  type: 'string',
                  description: 'Database name (equipment, another_db, etc.)',
                  enum: Object.keys(this.databases)
                },
                query: {
                  type: 'string',
                  description: 'The SQL query to execute.'
                }
              },
              required: ['database', 'query']
            },
          },
          {
            name: 'get_equipment_count',
            description: 'Gets the total count of equipment from the equipment database.',
            inputSchema: {
              type: 'object',
              properties: {
                database: {
                  type: 'string',
                  description: 'Database name',
                  enum: Object.keys(this.databases)
                }
              },
              required: ['database']
            },
          },
          {
            name: 'get_calibration_certificates_count',
            description: 'Gets the total count of calibration certificates from the equipment database.',
            inputSchema: {
              type: 'object',
              properties: {
                database: {
                  type: 'string',
                  description: 'Database name',
                  enum: Object.keys(this.databases)
                }
              },
              required: ['database']
            },
          },
        ],
      };
    });

    this.server.setRequestHandler(CallToolRequestSchema, async (request) => {
      const { name, arguments: args } = request.params;

      const dbConfig = this.databases[args.database];
      if (!dbConfig) {
        return {
          content: [
            {
              type: 'text',
              text: `Error: Database '${args.database}' not configured. Available: ${Object.keys(this.databases).join(', ')}`,
            },
          ],
          isError: true,
        };
      }

      const client = new Client(dbConfig);

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
                  text: `Total equipment in ${args.database}: ${equipmentResult.rows[0].count}`,
                },
              ],
            };

          case 'get_calibration_certificates_count':
            const certResult = await client.query('SELECT COUNT(*) FROM calibration_certificates');
            return {
              content: [
                {
                  type: 'text',
                  text: `Total calibration certificates in ${args.database}: ${certResult.rows[0].count}`,
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
    console.log('Multi-Database PostgreSQL MCP Server running on stdio');
  }
}

const server = new MultiDatabasePostgreSQLServer();
server.run().catch(console.error);
