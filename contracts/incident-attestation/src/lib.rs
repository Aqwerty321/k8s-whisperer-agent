#![no_std]

use soroban_sdk::{contract, contractimpl, contracttype, BytesN, Env, Symbol};

#[contracttype]
pub enum DataKey {
    Incident(Symbol),
}

#[contract]
pub struct IncidentAttestation;

#[contractimpl]
impl IncidentAttestation {
    pub fn anchor(env: Env, incident_id: Symbol, incident_hash: BytesN<32>) {
        let key = DataKey::Incident(incident_id);
        env.storage().persistent().set(&key, &incident_hash);
    }

    pub fn get(env: Env, incident_id: Symbol) -> Option<BytesN<32>> {
        let key = DataKey::Incident(incident_id);
        env.storage().persistent().get(&key)
    }
}
