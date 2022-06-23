using Urho;
using System;
using System.Reflection;
using System.Text;
using Newtonsoft.Json.Linq;
using System.IO;

/// <summary>
/// To export json this code is using Json.net. Please install like this on cli:
/// dotnet add package Newtonsoft.Json --version 13.0.1
/// </summary>

namespace Blender
{
    class DotNetComponentExporter
    {
        public static string GetExporterType(string typeName)
        {
            typeName = typeName.ToLower();
            if (typeName.StartsWith("int")) {
                return "int";
            }
            else if (typeName == "single" || typeName == "double") {
                return "float";
            }
            else if (typeName == "boolean") {
                return "bool";
            }
            else {
                return typeName;
            }
        }
        public string GenerateJSONNodetree(string outputFile, params Type[] types)
        {
            JObject main = new JObject();

            JArray trees = new JArray();
            main["trees"] = trees;
            JObject tree = new JObject();
            tree["id"] = "urho3dcomponents";
            tree["name"] = "Tree urho3dcomponents";
            tree["icon"] = "OUTLINER_OB_GROUP_INSTANCE";
            tree["exposedata_supported"] = "true";
            trees.Add(tree);


            JArray nodes = new JArray();
            tree["nodes"] = nodes;

            foreach (Type type in types) {
                JObject node = new JObject();
                node["id"] = $"urho3d_components__{type.Name}";
                node["name"] = $"{type.Name}";
                node["dotnet"] = true;
                node["dotnetType"] = type.AssemblyQualifiedName;

                var instance = Activator.CreateInstance(type);

                BindingFlags bindingFlags = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.Static;

                JArray jsonProps = new JArray();
                foreach (FieldInfo mInfo in type.GetFields(bindingFlags)) {
                    FieldAttributes fieldAttributes = mInfo.Attributes;
                    bool isSerializable = false;
                    bool disallowSerialzation = false;

                    foreach (Attribute attr in
                            Attribute.GetCustomAttributes(mInfo)) {
                        if (attr.GetType() == typeof(SerializeFieldAttribute)) {
                            isSerializable = true;
                        }
                        if (attr.GetType() == typeof(System.NonSerializedAttribute)) {
                            disallowSerialzation = true;
                            break;
                        }
                    }

                    // save only public or serializable fields
                    if (!(mInfo.IsPublic || isSerializable) || disallowSerialzation) continue;
                    // don't save constants
                    if ((fieldAttributes & FieldAttributes.Literal) == FieldAttributes.Literal) continue;

                    Type field_type = mInfo.FieldType;
                    string key = mInfo.Name;
                    object value = mInfo.GetValue(instance);

                    var typeName = GetExporterType(field_type.Name);
                    JObject jsonProp = new JObject();
                    jsonProp["name"] = key;
                    if (value != null) {
                    }
                    else {
                        jsonProp["default"] = "";
                    }

                    if (typeName == "Single") {
                        jsonProp["type"] = "float";
                        jsonProp["precission"] = 3;
                        jsonProp["subtype"] = "NONE";
                        jsonProp["default"] = value.ToString();
                    }
                    else if (field_type.IsEnum) {
                        jsonProp["type"] = "enum";
                        JArray elements = new JArray();
                        int i = 0;
                        int defaultId = 0;
                        foreach (var obj in Enum.GetValues(field_type)) {
                            if ((int)obj == (int)value) {
                                defaultId = i;
                            }
                            JObject element = new JObject();
                            element["id"] = obj.ToString();
                            element["name"] = obj.ToString();
                            element["description"] = obj.ToString();
                            element["icon"] = "ANIM";
                            element["number"] = i.ToString();
                            i++;
                            elements.Add(element);
                        }
                        jsonProp["elements"] = elements;
                        jsonProp["default"] = defaultId.ToString();
                    }
                    else {
                        jsonProp["type"] = typeName;
                        jsonProp["default"] = value != null ? value.ToString() : "";
                    }
                    jsonProps.Add(jsonProp);
                    // serializer.SetObjectValueToXmlElement(key, value);
                    // serializer.SetObjectValueToXmlElement($"{key}_type",field_type.Name);
                }
                node["props"] = jsonProps;
                string stResult = node.ToString();

                nodes.Add(node);
            }

            File.WriteAllText(outputFile, main.ToString());

            return main.ToString();
        }

        public void DeserializeFields(Component deserializer)
        {
            Type CompnentType = this.GetType();

            BindingFlags bindingFlags = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.Static;

            foreach (FieldInfo mInfo in CompnentType.GetFields(bindingFlags)) {
                FieldAttributes fieldAttributes = mInfo.Attributes;
                bool isSerializable = false;

                foreach (Attribute attr in Attribute.GetCustomAttributes(mInfo)) {
                    if (attr.GetType() == typeof(SerializeFieldAttribute)) {
                        isSerializable = true;
                    }
                }

                // load only public or serializable fields
                if (!(mInfo.IsPublic || isSerializable)) continue;
                // don't load constants
                if ((fieldAttributes & FieldAttributes.Literal) == FieldAttributes.Literal) continue;

                Type type = mInfo.FieldType;
                string key = mInfo.Name;

                // object value = deserializer.GetObjectValueFromXmlElement(type, key);
                // if (value != null)
                // {
                //     mInfo.SetValue(this, value);
                // }

            }
        }

    }

}
