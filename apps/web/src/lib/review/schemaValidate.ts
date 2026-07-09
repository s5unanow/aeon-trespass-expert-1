/**
 * A compact JSON-Schema validator — just enough of draft-2020-12 to validate a
 * built `patch_set.v1` export against the committed
 * `packages/schemas/jsonschema/patch_set_v1.schema.json`.
 *
 * We deliberately do NOT pull in `ajv` (not a project dependency) — the patch
 * schema uses a small, closed subset (`$ref`, `type`, `required`, `properties`,
 * `enum`, `pattern`, `items`, `anyOf`, `minimum`, `maximum`), all handled here.
 * The reader-side check complements the pipeline-side Pydantic parse.
 */

export interface SchemaError {
  path: string;
  message: string;
}

type Schema = Record<string, unknown>;

function isObject(v: unknown): v is Record<string, unknown> {
  return v !== null && typeof v === 'object' && !Array.isArray(v);
}

function resolveRef(ref: string, root: Schema): Schema {
  // Only local `#/$defs/Name` references occur in these schemas.
  const match = /^#\/\$defs\/(.+)$/.exec(ref);
  const defs = root.$defs;
  if (!match || !isObject(defs) || !isObject(defs[match[1]])) {
    throw new Error(`Unresolvable $ref: ${ref}`);
  }
  return defs[match[1]] as Schema;
}

function typeMatches(data: unknown, type: string): boolean {
  switch (type) {
    case 'object':
      return isObject(data);
    case 'array':
      return Array.isArray(data);
    case 'string':
      return typeof data === 'string';
    case 'number':
      return typeof data === 'number';
    case 'integer':
      return typeof data === 'number' && Number.isInteger(data);
    case 'boolean':
      return typeof data === 'boolean';
    case 'null':
      return data === null;
    default:
      return false;
  }
}

/** Validate `data` against `schema`; returns an empty array when valid. */
export function validateAgainstSchema(
  data: unknown,
  schema: Schema,
  root: Schema = schema,
  path = '$',
): SchemaError[] {
  if (typeof schema.$ref === 'string') {
    return validateAgainstSchema(data, resolveRef(schema.$ref, root), root, path);
  }

  if (Array.isArray(schema.anyOf)) {
    const branches = schema.anyOf as Schema[];
    const branchErrors = branches.map((s) => validateAgainstSchema(data, s, root, path));
    if (branchErrors.some((errs) => errs.length === 0)) return [];
    return [{ path, message: `does not match any of ${branches.length} allowed schemas` }];
  }

  const errors: SchemaError[] = [];

  if (typeof schema.type === 'string' && !typeMatches(data, schema.type)) {
    errors.push({ path, message: `expected type ${schema.type}, got ${describe(data)}` });
    return errors; // downstream keyword checks assume the type held
  }

  if (Array.isArray(schema.enum) && !(schema.enum as unknown[]).includes(data)) {
    errors.push({ path, message: `value ${JSON.stringify(data)} not in enum` });
  }

  if (typeof schema.pattern === 'string' && typeof data === 'string') {
    if (!new RegExp(schema.pattern).test(data)) {
      errors.push({ path, message: `does not match pattern ${schema.pattern}` });
    }
  }

  if (typeof schema.minimum === 'number' && typeof data === 'number' && data < schema.minimum) {
    errors.push({ path, message: `below minimum ${schema.minimum}` });
  }
  if (typeof schema.maximum === 'number' && typeof data === 'number' && data > schema.maximum) {
    errors.push({ path, message: `above maximum ${schema.maximum}` });
  }

  if (isObject(data)) {
    if (Array.isArray(schema.required)) {
      for (const key of schema.required as string[]) {
        if (data[key] === undefined) {
          errors.push({ path: `${path}.${key}`, message: 'required property missing' });
        }
      }
    }
    if (isObject(schema.properties)) {
      const props = schema.properties as Record<string, Schema>;
      for (const [key, sub] of Object.entries(props)) {
        if (data[key] !== undefined) {
          errors.push(...validateAgainstSchema(data[key], sub, root, `${path}.${key}`));
        }
      }
    }
  }

  if (Array.isArray(data) && isObject(schema.items)) {
    const itemSchema = schema.items as Schema;
    data.forEach((el, i) => {
      errors.push(...validateAgainstSchema(el, itemSchema, root, `${path}[${i}]`));
    });
  }

  return errors;
}

function describe(v: unknown): string {
  if (v === null) return 'null';
  if (Array.isArray(v)) return 'array';
  return typeof v;
}
