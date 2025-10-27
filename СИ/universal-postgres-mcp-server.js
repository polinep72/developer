const { Server } = require('@modelcontextprotocol/sdk/server/index.js');
const { StdioServerTransport } = require('@modelcontextprotocol/sdk/server/stdio.js');
const {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} = require('@modelcontextprotocol/sdk/types.js');
const { Client } = require('pg');

class UniversalPostgreSQLServer {
  constructor() {
    this.server = new Server(
      {
        name: 'universal-postgres-mcp-server',
        version: '1.0.0',
      },
      {
        capabilities: {
          tools: {},
        },
      }
    );

    // Базовая конфигурация (можно переопределить через переменные окружения)
    this.defaultConfig = {
      host: process.env.POSTGRES_HOST || '192.168.1.139',
      port: parseInt(process.env.POSTGRES_PORT) || 5432,
      user: process.env.POSTGRES_USER || 'postgres',
      password: process.env.POSTGRES_PASSWORD || '27915002'
    };

    this.setupToolHandlers();
  }

  setupToolHandlers() {
    this.server.setRequestHandler(ListToolsRequestSchema, async () => {
      return {
        tools: [
          {
            name: 'query_postgres',
            description: 'Executes a read-only SQL query on any PostgreSQL database.',
            inputSchema: {
              type: 'object',
              properties: {
                database: {
                  type: 'string',
                  description: 'Database name (equipment, production, etc.)'
                },
                query: {
                  type: 'string',
                  description: 'The SQL query to execute.'
                },
                host: {
                  type: 'string',
                  description: 'Database host (optional, uses default if not provided)'
                },
                port: {
                  type: 'string',
                  description: 'Database port (optional, uses default if not provided)'
                },
                user: {
                  type: 'string',
                  description: 'Database user (optional, uses default if not provided)'
                },
                password: {
                  type: 'string',
                  description: 'Database password (optional, uses default if not provided)'
                }
              },
              required: ['database', 'query']
            },
          },
          {
            name: 'list_databases',
            description: 'Lists all available databases on the server.',
            inputSchema: {
              type: 'object',
              properties: {
                host: {
                  type: 'string',
                  description: 'Database host (optional)'
                },
                port: {
                  type: 'string',
                  description: 'Database port (optional)'
                }
              }
            },
          },
          {
            name: 'get_database_info',
            description: 'Gets information about a specific database (tables, sizes, etc.).',
            inputSchema: {
              type: 'object',
              properties: {
                database: {
                  type: 'string',
                  description: 'Database name'
                },
                host: {
                  type: 'string',
                  description: 'Database host (optional)'
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

      try {
        switch (name) {
          case 'query_postgres':
            return await this.executeQuery(args);
          
          case 'list_databases':
            return await this.listDatabases(args);
          
          case 'get_database_info':
            return await this.getDatabaseInfo(args);
          
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
      }
    });
  }

  async executeQuery(args) {
    const config = {
      ...this.defaultConfig,
      database: args.database,
      ...(args.host && { host: args.host }),
      ...(args.port && { port: parseInt(args.port) }),
      ...(args.user && { user: args.user }),
      ...(args.password && { password: args.password })
    };

    const client = new Client(config);
    
    try {
      await client.connect();
      const result = await client.query(args.query);
      
      return {
        content: [
          {
            type: 'text',
            text: `Database: ${args.database}\nQuery: ${args.query}\n\nResults:\n${JSON.stringify(result.rows, null, 2)}`,
          },
        ],
      };
    } finally {
      await client.end();
    }
  }

  async listDatabases(args) {
    const config = {
      ...this.defaultConfig,
      database: 'postgres', // Подключаемся к системной БД
      ...(args.host && { host: args.host }),
      ...(args.port && { port: parseInt(args.port) })
    };

    const client = new Client(config);
    
    try {
      await client.connect();
      const result = await client.query(`
        SELECT 
          datname as database_name,
          pg_size_pretty(pg_database_size(datname)) as size,
          (SELECT count(*) FROM pg_tables WHERE schemaname = 'public') as tables_count
        FROM pg_database 
        WHERE datistemplate = false
        ORDER BY datname
      `);
      
      return {
        content: [
          {
            type: 'text',
            text: `Available databases:\n${result.rows.map(row => 
              `- ${row.database_name} (${row.size}, ~${row.tables_count} tables)`
            ).join('\n')}`,
          },
        ],
      };
    } finally {
      await client.end();
    }
  }

  async getDatabaseInfo(args) {
    const config = {
      ...this.defaultConfig,
      database: args.database,
      ...(args.host && { host: args.host })
    };

    const client = new Client(config);
    
    try {
      await client.connect();
      
      // Получаем информацию о таблицах
      const tablesResult = await client.query(`
        SELECT 
          table_name,
          pg_size_pretty(pg_total_relation_size(table_name::regclass)) as size
        FROM information_schema.tables 
        WHERE table_schema = 'public'
        ORDER BY pg_total_relation_size(table_name::regclass) DESC
        LIMIT 10
      `);
      
      // Получаем общую информацию о БД
      const dbSizeResult = await client.query(`
        SELECT pg_size_pretty(pg_database_size(current_database())) as database_size
      `);
      
      return {
        content: [
          {
            type: 'text',
            text: `Database: ${args.database}\nSize: ${dbSizeResult.rows[0].database_size}\n\nTop 10 tables:\n${tablesResult.rows.map(row => 
              `- ${row.table_name} (${row.size})`
            ).join('\n')}`,
          },
        ],
      };
    } finally {
      await client.end();
    }
  }

  async run() {
    const transport = new StdioServerTransport();
    await this.server.connect(transport);
    console.log('Universal PostgreSQL MCP Server running on stdio');
  }
}

const server = new UniversalPostgreSQLServer();
server.run().catch(console.error);
