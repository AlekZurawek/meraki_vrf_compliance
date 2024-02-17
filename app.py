import requests

# Replace with your Meraki API key
MERAKI_API_KEY = ‘Your API Key goes here’

# Replace with your Organization ID
ORGANIZATION_ID = ‘Your Org ID goes here’

# Meraki base URL
MERAKI_BASE_URL = 'https://api.meraki.com/api/v1'

# Set up headers for HTTP request
headers = {
    'X-Cisco-Meraki-API-Key': MERAKI_API_KEY,
    'Content-Type': 'application/json'
}

def read_vlan_configurations(file_path):
    vlan_configs = {}
    with open(file_path, 'r') as file:
        for line in file:
            parts = line.strip().split(',')
            if len(parts) == 2:
                object_group, vlan_id = parts
                vlan_configs[vlan_id.strip()] = object_group.strip()
    return vlan_configs

def get_networks_with_appliance(organization_id):
    url = f'{MERAKI_BASE_URL}/organizations/{organization_id}/networks'
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        networks = response.json()
        return [network for network in networks if 'appliance' in network.get('productTypes', [])]
    return []

def get_vlans_for_network(network_id):
    url = f'{MERAKI_BASE_URL}/networks/{network_id}/appliance/vlans'
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()
    return []

def get_policy_objects(organization_id):
    url = f'{MERAKI_BASE_URL}/organizations/{organization_id}/policyObjects'
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()
    return []

def create_policy_object(organization_id, name, cidr):
    url = f'{MERAKI_BASE_URL}/organizations/{organization_id}/policyObjects'
    data = {
        'name': name.replace('/', '_').replace('.', '_'),
        'cidr': cidr,
        'category': 'network',
        'type': 'cidr'
    }
    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 201:
        print(f"Policy object created - ID: {response.json()['id']}, Name: {name}, CIDR: {cidr}")
        return response.json()
    else:
        print(f"Failed to create policy object - Name: {name}, CIDR: {cidr}")
        return None

def create_policy_object_group(organization_id, name, object_ids):
    url = f'{MERAKI_BASE_URL}/organizations/{organization_id}/policyObjects/groups'
    data = {
        'name': name,
        'objectIds': object_ids,
        'category': 'NetworkObjectGroup'
    }
    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 201:
        print(f"Policy object group created - ID: {response.json()['id']}, Name: {name}, Object IDs: {object_ids}")
        return response.json()

def get_policy_object_groups(organization_id):
    url = f'{MERAKI_BASE_URL}/organizations/{organization_id}/policyObjects/groups'
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()
    return []

def update_policy_object_group(organization_id, group_id, name, object_ids):
    url = f'{MERAKI_BASE_URL}/organizations/{organization_id}/policyObjects/groups/{group_id}'
    data = {
        'name': name,
        'objectIds': object_ids
    }
    response = requests.put(url, headers=headers, json=data)
    if response.status_code == 200:
        print(f"Policy object group updated - ID: {response.json()['id']}, Name: {name}, Object IDs: {object_ids}")
    return response.json()

def match_vlans_and_print(vlan_configs, networks, policy_objects):
    policy_object_ids = {}
    for network in networks:
        vlans = get_vlans_for_network(network['id'])
        for vlan in vlans:
            vlan_id = str(vlan['id'])
            if vlan_id in vlan_configs:
                print(f"Match found - Network ID: {network['id']}, Name: {network['name']}, VLAN ID: {vlan_id}, Subnet: {vlan['subnet']}")
                policy_object = next((po for po in policy_objects if po['cidr'] == vlan['subnet']), None)
                if policy_object:
                    print(f"Policy object match found - ID: {policy_object['id']}, Name: {policy_object['name']}, CIDR: {policy_object['cidr']}")
                    if vlan_configs[vlan_id] not in policy_object_ids:
                        policy_object_ids[vlan_configs[vlan_id]] = [policy_object['id']]
                    else:
                        policy_object_ids[vlan_configs[vlan_id]].append(policy_object['id'])
                else:
                    print(f"Policy object not found, creating one - CIDR: {vlan['subnet']}")
                    new_po = create_policy_object(ORGANIZATION_ID, vlan['subnet'].replace('/', '_'), vlan['subnet'])
                    if vlan_configs[vlan_id] not in policy_object_ids:
                        policy_object_ids[vlan_configs[vlan_id]] = [new_po['id']]
                    else:
                        policy_object_ids[vlan_configs[vlan_id]].append(new_po['id'])
    return policy_object_ids

def main():
    vlan_configs = read_vlan_configurations('vrf.conf')
    networks = get_networks_with_appliance(ORGANIZATION_ID)
    policy_objects = get_policy_objects(ORGANIZATION_ID)
    policy_object_ids = match_vlans_and_print(vlan_configs, networks, policy_objects)
    policy_object_groups = get_policy_object_groups(ORGANIZATION_ID)
    
    all_assigned_ids = [id for ids in policy_object_ids.values() for id in ids]

    for group_name, object_ids in policy_object_ids.items():
        group = next((g for g in policy_object_groups if g['name'] == group_name), None)
        if group:
            print(f"Policy object group found - ID: {group['id']}, Name: {group['name']}")
            all_ids = group['objectIds']
            for object_id in object_ids:
                if object_id not in all_ids:
                    all_ids.append(object_id)
            update_policy_object_group(ORGANIZATION_ID, group['id'], group['name'], all_ids)
        else:
            print(f"Policy object group not found, creating one - Name: {group_name}")
            create_policy_object_group(ORGANIZATION_ID, group_name, object_ids)

    # creating policy objects for all other non-matched vlans
    unassigned_object_ids = []
    for network in networks:
        vlans = get_vlans_for_network(network['id'])
        for vlan in vlans:
            subnet = vlan['subnet']
            policy_object = next((po for po in policy_objects if po['cidr'] == subnet), None)
            if not policy_object:
                print(f"Creating policy object for non-matched VLAN - Subnet: {subnet}")
                new_po = create_policy_object(ORGANIZATION_ID, subnet.replace('/', '_').replace('.', '_'), subnet)
                if new_po:
                    unassigned_object_ids.append(new_po['id'])
            else:
                if policy_object['id'] not in all_assigned_ids and policy_object['name'].replace('_', '').isdigit():
                    unassigned_object_ids.append(policy_object['id'])

    # creating "unassigned" policy object group
    if unassigned_object_ids:
        unassigned_group = next((g for g in policy_object_groups if g['name'] == 'unassigned'), None)
        if unassigned_group:
            print(f"Policy object group 'unassigned' found - ID: {unassigned_group['id']}")
            all_ids = unassigned_group['objectIds']
            for object_id in unassigned_object_ids:
                if object_id not in all_ids:
                    all_ids.append(object_id)
            update_policy_object_group(ORGANIZATION_ID, unassigned_group['id'], 'unassigned', all_ids)
        else:
            print(f"Policy object group 'unassigned' not found, creating one")
            create_policy_object_group(ORGANIZATION_ID, 'unassigned', unassigned_object_ids)

if __name__ == "__main__":
    main()
